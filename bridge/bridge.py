#!/usr/bin/env python3

import base64
import email.parser
import hashlib
import json
import os
import signal
import smtplib
import socketserver
import ssl
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path


LISTEN_PORT = int(os.environ["MAILSTACK_BRIDGE_PORT"])          # stack.env
ROUTES_FILE = Path(os.environ.get("BRIDGE_ROUTES_FILE", "/config/bridge-routes.json"))   # tests set it
MAX_HEADER_LINE = 8192
MAX_MESSAGE = int(os.environ["MAILSTACK_MAX_MESSAGE_BYTES"])   # stack.env


@dataclass(frozen=True)
class Config:
    jmap_session: str
    jmap_user: str
    jmap_password: str
    provenance_url: str


@dataclass(frozen=True)
class Route:
    account: str
    address: str
    stalwart_user: str
    active: bool
    # Provider folders whose mail goes through the account's filter
    # (inbound_sieve.folders, casefolded); the others are imported as they are.
    sieve_folders: frozenset


@dataclass(frozen=True)
class JmapSession:
    account_id: str
    api_url: str
    upload_url: str
    download_url: str


@dataclass(frozen=True)
class DeliveryRequest:
    account: str
    mailbox: str
    sender: str
    raw: bytes
    # From the provider's folder list (handoff): the folder's hierarchy
    # separator ("" when it has none) and its role (junk, sent, drafts,
    # trash, archive; folders.yaml or the provider's mark).
    delimiter: str
    role: str = ""
    # The provider's folders are labels (Gmail): a mail seen in another
    # folder gets that folder too, it is not moved.
    labels: bool = False


@dataclass(frozen=True)
class DeliveryResult:
    method: str
    account_id: str | None = None
    email_id: str | None = None


def load_config():
    return Config(
        jmap_session=os.environ["JMAP_SESSION"],
        jmap_user=os.environ["JMAP_USER"],
        jmap_password=os.environ["JMAP_PASSWORD"],
        provenance_url=os.environ["PROVENANCE_URL"].rstrip("/"),
    )


def load_routes(path):
    with path.open("r", encoding="utf-8") as f:
        raw_routes = json.load(f)

    routes = {}

    for account, raw in raw_routes.items():
        try:
            route = Route(
                account=account,
                address=raw["address"],
                stalwart_user=raw["stalwart_user"],
                active=raw["active"],
                sieve_folders=frozenset(
                    name.casefold()
                    for name in raw["sieve_folders"]
                ),
            )
        except KeyError as exc:
            raise RuntimeError(
                f"route {account!r} missing {exc.args[0]!r}"
            ) from exc

        if not route.address:
            raise RuntimeError(
                f"route {account!r} has empty address"
            )

        if not route.stalwart_user:
            raise RuntimeError(
                f"route {account!r} has empty Stalwart user"
            )

        routes[account] = route

    return routes


CONFIG = load_config()
ROUTES = load_routes(ROUTES_FILE)

class ProtocolError(Exception):
    pass


class JmapError(Exception):
    def __init__(self, error):
        super().__init__(str(error))
        self.error = error

    @property
    def type(self):
        if isinstance(self.error, dict):
            return self.error.get("type")
        return None


class JmapClient:
    def __init__(self, config):
        self.config = config
        # Stalwart on the private Docker network, with its own certificate
        # (DECISIONS.md, "Inside the stack, TLS to Stalwart is not verified").
        self.ssl_context = ssl._create_unverified_context()
        self._cache_lock = threading.RLock()
        self._session_cache = {}
        self._mailbox_cache = {}
        self._mailbox_locks = {}
        self._message_index = {}

    def auth_header(self, target_user):
        username = f"{target_user}%{self.config.jmap_user}"
        token = base64.b64encode(
            f"{username}:{self.config.jmap_password}".encode()
        ).decode()
        return f"Basic {token}"

    def request(
        self,
        url,
        target_user,
        data=None,
        content_type="application/json",
    ):
        req = urllib.request.Request(url, data=data)
        req.add_header(
            "Authorization",
            self.auth_header(target_user),
        )

        if data is not None:
            req.add_header("Content-Type", content_type)

        kwargs = {"timeout": 30}
        if url.lower().startswith("https://"):
            kwargs["context"] = self.ssl_context

        with urllib.request.urlopen(
            req,
            **kwargs,
        ) as response:
            return json.loads(response.read())

    def call(self, api_url, target_user, method, args):
        body = json.dumps({
            "using": [
                "urn:ietf:params:jmap:core",
                "urn:ietf:params:jmap:mail",
            ],
            "methodCalls": [[method, args, "c1"]],
        }).encode()

        result = self.request(
            api_url,
            target_user,
            body,
        )
        name, response, _ = result["methodResponses"][0]

        if name == "error":
            raise JmapError(response)

        return response

    def session(self, target_user):
        with self._cache_lock:
            cached = self._session_cache.get(target_user)
            if cached is not None:
                return cached

        raw = self.request(
            self.config.jmap_session,
            target_user,
        )

        if raw.get("username") != target_user:
            raise RuntimeError(
                "JMAP impersonation returned unexpected username"
            )

        matches = [
            account_id
            for account_id, account
            in raw.get("accounts", {}).items()
            if account.get("name") == target_user
        ]

        if len(matches) != 1:
            raise RuntimeError(
                f"expected exactly one JMAP account for "
                f"{target_user!r}, found {len(matches)}"
            )

        account_id = matches[0]
        session = JmapSession(
            account_id=account_id,
            api_url=raw["apiUrl"],
            upload_url=raw["uploadUrl"].replace("{accountId}", account_id),
            download_url=raw["downloadUrl"].replace("{accountId}", account_id),
        )

        with self._cache_lock:
            self._session_cache[target_user] = session

        return session

    def invalidate_session(self, target_user):
        with self._cache_lock:
            session = self._session_cache.pop(
                target_user,
                None,
            )

            if session is None:
                return

            self._mailbox_cache.pop(
                session.account_id,
                None,
            )
            self._mailbox_locks.pop(
                session.account_id,
                None,
            )
            self._message_index.pop(session.account_id, None)

    def mailbox_lock(self, account_id):
        with self._cache_lock:
            lock = self._mailbox_locks.get(account_id)

            if lock is None:
                lock = threading.RLock()
                self._mailbox_locks[account_id] = lock

            return lock

    def mailbox_inventory(
        self,
        session,
        target_user,
    ):
        result = self.call(
            session.api_url,
            target_user,
            "Mailbox/get",
            {
                "accountId": session.account_id,
                "properties": [
                    "id",
                    "name",
                    "parentId",
                    "role",
                ],
            },
        )

        return result["list"]

    def refresh_mailbox_cache(
        self,
        session,
        target_user,
    ):
        boxes = self.mailbox_inventory(
            session,
            target_user,
        )
        cache = {}

        for box in boxes:
            cache[
                (box.get("parentId"), box["name"])
            ] = box["id"]

            role = box.get("role")
            if role:
                cache[("ROLE", role)] = box["id"]

        with self._cache_lock:
            self._mailbox_cache[
                session.account_id
            ] = cache

    def mailbox_cache(
        self,
        session,
        target_user,
    ):
        with self._cache_lock:
            cache = self._mailbox_cache.get(
                session.account_id
            )

        if cache is None:
            self.refresh_mailbox_cache(
                session,
                target_user,
            )

            with self._cache_lock:
                cache = self._mailbox_cache[
                    session.account_id
                ]

        return cache

    def create_mailbox(
        self,
        session,
        target_user,
        name,
        parent_id,
    ):
        create_id = "new"

        result = self.call(
            session.api_url,
            target_user,
            "Mailbox/set",
            {
                "accountId": session.account_id,
                "create": {
                    create_id: {
                        "name": name,
                        "parentId": parent_id,
                        # Subscribed, so IMAP clients (Roundcube lists
                        # only subscribed folders) show it at once. Set
                        # only at creation: a user's later unsubscribe
                        # stays.
                        "isSubscribed": True,
                    }
                },
            },
        )

        created = result.get(
            "created",
            {},
        ).get(create_id)

        if not created:
            raise RuntimeError(
                f"Mailbox creation failed: {result}"
            )

        return created["id"]

    def mailbox_role_of(self, session, target_user, mailbox_id):
        cache = self.mailbox_cache(session, target_user)
        for key, value in cache.items():
            if key[0] == "ROLE" and value == mailbox_id:
                return key[1]
        return None

    def resolve_mailbox(
        self,
        session,
        target_user,
        source_name,
        role,
        delimiter,
    ):
        # Discovery and creation are serialized within one
        # JMAP account. Different accounts remain independent.
        with self.mailbox_lock(session.account_id):
            cache = self.mailbox_cache(
                session,
                target_user,
            )

            # The role getmail found for the provider folder (its special-use
            # flag, or folders.yaml); names mean nothing by themselves.
            if role:
                mailbox_id = cache.get(("ROLE", role))
                if mailbox_id:
                    return mailbox_id

            parts = (
                [source_name]
                if not delimiter
                else source_name.split(delimiter)
            )

            parent_id = None

            for part in parts:
                if (
                    parent_id is None
                    and part.upper() == "INBOX"
                ):
                    mailbox_id = cache.get(
                        ("ROLE", "inbox")
                    )
                else:
                    mailbox_id = cache.get(
                        (parent_id, part)
                    )

                if mailbox_id:
                    parent_id = mailbox_id
                    continue

                parent_id = self.create_mailbox(
                    session,
                    target_user,
                    part,
                    parent_id,
                )

                # Creation changes authoritative mailbox state.
                self.refresh_mailbox_cache(
                    session,
                    target_user,
                )
                cache = self.mailbox_cache(
                    session,
                    target_user,
                )

            return parent_id

    def upload_message(
        self,
        session,
        target_user,
        raw,
    ):
        req = urllib.request.Request(
            session.upload_url,
            data=raw,
            method="POST",
        )
        req.add_header(
            "Authorization",
            self.auth_header(target_user),
        )
        req.add_header(
            "Content-Type",
            "message/rfc822",
        )

        kwargs = {"timeout": 30}
        if session.upload_url.lower().startswith("https://"):
            kwargs["context"] = self.ssl_context

        with urllib.request.urlopen(
            req,
            **kwargs,
        ) as response:
            uploaded = json.loads(response.read())

        return uploaded["blobId"]

    def import_email(
        self,
        session,
        target_user,
        blob_id,
        mailbox_id,
    ):
        result = self.call(
            session.api_url,
            target_user,
            "Email/import",
            {
                "accountId": session.account_id,
                "emails": {
                    "msg": {
                        "blobId": blob_id,
                        "mailboxIds": {
                            mailbox_id: True
                        },
                    }
                },
            },
        )

        created = result.get(
            "created",
            {},
        ).get("msg")

        if not created:
            raise RuntimeError(
                f"Email/import failed: {result}"
            )

        return created["id"]

    def download_blob(self, session, target_user, blob_id):
        url = (
            session.download_url
            .replace("{blobId}", blob_id)
            .replace("{name}", "message.eml")
            .replace("{type}", "message/rfc822")
        )
        req = urllib.request.Request(url)
        req.add_header("Authorization", self.auth_header(target_user))
        kwargs = {"timeout": 30}
        if url.lower().startswith("https://"):
            kwargs["context"] = self.ssl_context
        with urllib.request.urlopen(req, **kwargs) as response:
            data = response.read(MAX_MESSAGE + 1)
        if len(data) > MAX_MESSAGE:
            raise RuntimeError(f"stored mail {blob_id} is larger than MAILSTACK_MAX_MESSAGE_BYTES")
        return data

    def emails_get(self, session, target_user, ids, properties):
        found = {}
        for start in range(0, len(ids), 500):
            result = self.call(session.api_url, target_user, "Email/get", {
                "accountId": session.account_id,
                "ids": ids[start:start + 500],
                "properties": properties,
            })
            for item in result.get("list", []):
                found[item["id"]] = item
        return found

    def message_ids(self, session, target_user):
        """account's Message-ID -> set of Email ids, kept current with
        Email/changes. Stalwart 0.16 cannot search by Message-ID (the JMAP
        header filter and IMAP SEARCH HEADER find nothing), so the bridge
        keeps this index itself: loaded once per account, then updated."""
        with self.mailbox_lock(session.account_id):
            with self._cache_lock:
                index = self._message_index.get(session.account_id)
            if index is None:
                index = self.load_message_index(session, target_user)
            else:
                index = self.update_message_index(session, target_user, index)
            with self._cache_lock:
                self._message_index[session.account_id] = index
            return index

    def load_message_index(self, session, target_user):
        state = self.call(session.api_url, target_user, "Email/get", {
            "accountId": session.account_id, "ids": [], "properties": ["id"],
        })["state"]
        ids, position = [], 0
        while True:
            page = self.call(session.api_url, target_user, "Email/query", {
                "accountId": session.account_id, "position": position, "limit": 1000,
            }).get("ids") or []
            ids += page
            position += len(page)
            if len(page) < 1000:
                break
        index = {"state": state, "by_mid": {}, "mid_of": {}}
        self.index_add(index, self.emails_get(session, target_user, ids, ["messageId"]))
        print(f"INDEX account={session.account_id} mails={len(ids)}", flush=True)
        return index

    def update_message_index(self, session, target_user, index):
        while True:
            try:
                changes = self.call(session.api_url, target_user, "Email/changes", {
                    "accountId": session.account_id, "sinceState": index["state"],
                    "maxChanges": 5000,
                })
            except JmapError as exc:
                if exc.type == "cannotCalculateChanges":
                    return self.load_message_index(session, target_user)
                raise
            for email_id in changes.get("destroyed", []):
                self.index_remove(index, email_id)
            created = changes.get("created", [])
            if created:
                self.index_add(index, self.emails_get(session, target_user, created, ["messageId"]))
            index["state"] = changes["newState"]
            if not changes.get("hasMoreChanges"):
                return index

    @staticmethod
    def index_add(index, emails):
        for email_id, item in emails.items():
            for mid in item.get("messageId") or []:
                index["by_mid"].setdefault(mid, set()).add(email_id)
                index["mid_of"].setdefault(email_id, set()).add(mid)

    @staticmethod
    def index_remove(index, email_id):
        for mid in index["mid_of"].pop(email_id, set()):
            ids = index["by_mid"].get(mid)
            if ids:
                ids.discard(email_id)
                if not ids:
                    del index["by_mid"][mid]

    def set_mailboxes(self, session, target_user, email_id, patch):
        result = self.call(session.api_url, target_user, "Email/set", {
            "accountId": session.account_id, "update": {email_id: patch},
        })
        if email_id not in (result.get("updated") or {}):
            raise RuntimeError(f"Email/set failed: {result.get('notUpdated')}")

    def import_new(self, raw, mailbox_id, session, target_user):
        blob_id = self.upload_message(session, target_user, raw)
        email_id = self.import_email(session, target_user, blob_id, mailbox_id)
        with self._cache_lock:
            index = self._message_index.get(session.account_id)
            if index is not None:
                mid = source_message_id(raw)
                if mid:
                    self.index_add(index, {email_id: {"messageId": [mid]}})
        return email_id

    def forget_mailboxes(self, target_user):
        """Drop the account's folder list: folders are also made, renamed and
        deleted elsewhere (webmail, the filter's fileinto :create, resieve)."""
        account_id = self.session(target_user).account_id
        with self._cache_lock:
            self._mailbox_cache.pop(account_id, None)

    def with_session(self, target_user, work):
        """work(session); once more with a fresh session when Stalwart
        no longer knows the cached account (account recreated)."""
        try:
            return work(self.session(target_user))
        except JmapError as exc:
            if exc.type not in {"forbidden", "accountNotFound"}:
                raise
            self.invalidate_session(target_user)
            return work(self.session(target_user))


JMAP = JmapClient(CONFIG)


def read_line(rfile):
    line = rfile.readline(MAX_HEADER_LINE + 1)

    if not line:
        raise ProtocolError("unexpected EOF")

    if len(line) > MAX_HEADER_LINE:
        raise ProtocolError("header line too long")

    if not line.endswith(b"\n"):
        raise ProtocolError("unterminated header")

    return line.rstrip(b"\r\n").decode("utf-8")


def parse_field(line, name, allow_empty=False):
    prefix = name + ":"

    if not line.startswith(prefix):
        raise ProtocolError(f"expected {name}")

    value = line[len(prefix):]

    if not value and not allow_empty:
        raise ProtocolError(f"empty {name}")

    return value


def read_delivery_request(rfile):
    account = parse_field(
        read_line(rfile),
        "ACCOUNT",
    )
    mailbox = parse_field(
        read_line(rfile),
        "MAILBOX",
    )
    sender = parse_field(
        read_line(rfile),
        "SENDER",
        allow_empty=True,
    )

    # From the provider's folder list: DELIMITER (hierarchy separator, NIL
    # for none; required), ROLE (folders.py writes it lowercase; a role the
    # bridge has no use for changes nothing) and LABELS:yes.
    extra = {}
    while True:
        line = read_line(rfile)
        if line == "":
            break
        name, sep, value = line.partition(":")
        if not sep or name not in ("ROLE", "DELIMITER", "LABELS"):
            raise ProtocolError(f"unknown field {name!r}")
        if name in extra:
            raise ProtocolError(f"field {name} twice")
        extra[name] = value
    if "DELIMITER" not in extra:
        raise ProtocolError("expected DELIMITER")
    delimiter = extra["DELIMITER"]
    if delimiter != "NIL" and len(delimiter) != 1:
        raise ProtocolError(f"DELIMITER is one character or NIL, not {delimiter!r}")
    if extra.get("LABELS", "yes") != "yes":
        raise ProtocolError("LABELS is only ever yes")

    raw = rfile.read(MAX_MESSAGE + 1)

    if not raw:
        raise ProtocolError("empty message")

    if len(raw) > MAX_MESSAGE:
        raise ProtocolError("message too large")

    return DeliveryRequest(
        account=account,
        mailbox=mailbox,
        sender=sender,
        raw=raw,
        role=extra.get("ROLE", ""),
        delimiter=delimiter if delimiter != "NIL" else "",
        labels=extra.get("LABELS") == "yes",
    )


def route_for_account(account):
    route = ROUTES.get(account)

    if route is None:
        raise ProtocolError("unknown account")

    if not route.active:
        raise ProtocolError("inactive account")

    return route


def source_message_id(raw):
    """The Message-ID without angle brackets, as JMAP reports it."""
    headers = email.parser.BytesHeaderParser().parsebytes(raw)
    value = (headers.get("Message-ID") or "").strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    return value or None


GETMAIL_ADDED = (b"return-path:", b"delivered-to:")


def getmail_source(raw):
    """The message as the provider has it: raw without the header lines
    getmail puts in front when it delivers (Return-Path, Delivered-To and
    its own Received line, "... with IMAP4-SSL getmail6 msgid:..."), which
    differ between two fetches of the same message. Anything else, including
    the provider's own Received lines, is kept."""
    pos = 0
    while pos < len(raw):
        end = raw.find(b"\n", pos)
        if end == -1:
            break
        # The header field with its continuation lines.
        nxt = end + 1
        while nxt < len(raw) and raw[nxt:nxt + 1] in (b" ", b"\t"):
            more = raw.find(b"\n", nxt)
            if more == -1:
                break
            end, nxt = more, more + 1
        field = raw[pos:nxt]
        lower = field.lower()
        if lower.startswith(GETMAIL_ADDED) or (
            lower.startswith(b"received:") and b"getmail" in lower
        ):
            pos = nxt
            continue
        break
    return raw[pos:]


# Provenance can be briefly unavailable (restart, startup). By then the mail
# is already imported, so the record is retried here: getmail would fetch it
# again only at its next pass over that folder. Worst case 120 s of pauses
# plus 9 attempts of PROTECT_TIMEOUT: 165 s, within getmail's stop wait
# (getmail/entrypoint.sh STOP_WAIT, 170 s), the handoff's wait (300 s) and
# both services' stop_grace_period (compose.yaml, 3 min).
PROTECT_RETRY_SECONDS = (1, 2, 4, 8, 15, 30, 30, 30)
PROTECT_TIMEOUT = 5


def protect_provider_placement(account, email_id):
    for attempt, pause in enumerate((0, *PROTECT_RETRY_SECONDS)):
        if pause:
            time.sleep(pause)
        try:
            protect_once(account, email_id)
            if attempt:
                print(
                    f"PROTECTED account={account!r} email_id={email_id} "
                    f"after {attempt} retries",
                    flush=True,
                )
            return
        except Exception as exc:
            if attempt == len(PROTECT_RETRY_SECONDS):
                raise
            print(
                f"RETRY provenance for account={account!r} "
                f"email_id={email_id}: {type(exc).__name__}: {exc}",
                flush=True,
            )


def protect_once(account, email_id):

    payload = json.dumps({
        "account": account,
        "email_id": email_id,
        "reason": "provider-mailbox",
    }).encode("utf-8")

    request = urllib.request.Request(
        CONFIG.provenance_url + "/protect",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # urlopen raises for any answer other than 2xx.
    with urllib.request.urlopen(request, timeout=PROTECT_TIMEOUT):
        pass


def header_block_end(raw):
    """(end of the header block, line separator)."""
    for boundary, separator in ((b"\r\n\r\n", b"\r\n"), (b"\n\n", b"\n")):
        pos = raw.find(boundary)
        if pos != -1:
            return pos, separator
    raise RuntimeError("message has no header/body boundary")


def ensure_message_id(raw):
    """A mail without Message-ID gets one derived from its content, so the
    same mail fetched again gets the same one (RFC 5322 only says SHOULD;
    cron mails, devices, some spam have none)."""
    if source_message_id(raw):
        return raw
    _, separator = header_block_end(raw)
    digest = hashlib.sha256(getmail_source(raw)).hexdigest()[:40]
    return b"Message-ID: <" + digest.encode() + b"@mailstack.invalid>" + separator + raw


IDENTITY_HEADERS = ("message-id", "from", "date", "subject")


def mail_identity(raw):
    """What makes two stored copies the same mail: Message-ID, From, Date,
    Subject and the exact body. Header lines added in front on the way in
    (getmail's, Stalwart's Received/Delivered-To/X-Spam-*) do not count, so
    a copy delivered over SMTP matches one imported from a folder."""
    end, separator = header_block_end(raw)
    headers = email.parser.BytesHeaderParser().parsebytes(raw[:end] + separator * 2)
    body = raw[end:].replace(b"\r\n", b"\n").strip()
    values = tuple(" ".join(str(headers.get(name, "")).split()) for name in IDENTITY_HEADERS)
    return values + (hashlib.sha256(body).hexdigest(),)


def provenance_protected(account, email_ids):
    """Which of email_ids are recorded as placed by a human."""
    if not email_ids:
        return set()
    request = urllib.request.Request(
        CONFIG.provenance_url + "/protected",
        data=json.dumps({"account": account, "email_ids": sorted(email_ids)}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return set(json.loads(response.read())["protected"])


JUNK_HEADER = b"X-Mailstack-Provider-Folder"
JUNK_PORT = int(os.environ["MAILSTACK_JUNK_PORT"])               # stack.env


def without_header(raw, name):
    """raw without any header field `name` (with its continuation lines)."""
    end, separator = header_block_end(raw)
    lines = raw[:end].split(separator)
    kept, dropping = [], False
    prefix = name.lower() + b":"
    for line in lines:
        if line[:1] in (b" ", b"\t"):
            if not dropping:
                kept.append(line)
            continue
        dropping = line.lower().startswith(prefix)
        if not dropping:
            kept.append(line)
    return separator.join(kept) + raw[end:]


def deliver_smtp(raw, sender, address, junk=False):
    """Normal delivery: Stalwart runs the account's filter. Mail from the
    provider's Junk goes to the second port, where Stalwart's spam filter
    runs and our rule (header below) makes it spam: the filter still decides,
    and what it leaves in INBOX goes to Junk. No delivery reports: the
    provider already accepted the mail, a bounce would be backscatter."""
    domain = address.rsplit("@", 1)[1]
    raw = without_header(without_header(raw, JUNK_HEADER), b"Return-Path")
    if junk:
        _, separator = header_block_end(raw)
        raw = JUNK_HEADER + b": Junk" + separator + raw
    with smtplib.SMTP(
        "stalwart",
        JUNK_PORT if junk else 25,
        local_hostname=f"mail-bridge.{domain}",
        timeout=30,
    ) as smtp:
        smtp.ehlo()
        # Stalwart offers DSN to the bridge (stalwart-provision's
        # MtaExtensions); without it a failed delivery could bounce to the
        # sender, so the mail waits (getmail tries again) instead.
        if not smtp.has_extn("dsn"):
            raise RuntimeError("Stalwart offers the bridge no DSN (stalwart-provision: MtaExtensions)")
        options = ["NOTIFY=NEVER"]
        refused = smtp.sendmail(sender, [address], raw, rcpt_options=options)
    if refused:
        raise RuntimeError(f"SMTP recipients refused: {refused}")


def same_mail_copies(session, target_user, raw):
    """Copies of this mail already in the account: {email_id: properties}."""
    mid = source_message_id(raw)
    ids = sorted(JMAP.message_ids(session, target_user)["by_mid"].get(mid, ()))
    if not ids:
        return {}, {}
    same_id = JMAP.emails_get(session, target_user, ids, ["mailboxIds", "blobId"])
    wanted = mail_identity(raw)
    identical = {}
    for email_id, item in same_id.items():
        stored = JMAP.download_blob(session, target_user, item["blobId"])
        if mail_identity(stored) == wanted:
            identical[email_id] = item
    return same_id, identical


OUTGOING_ROLES = ("sent", "drafts")
# Places, not labels, even at a provider with labels (Gmail): a mail marked
# as spam or deleted there leaves its other folders, and comes back out of
# them as a whole ("not spam", restored from the trash).
EXCLUSIVE_ROLES = ("junk", "trash")


def received_copies(session, user, copies):
    """The copies that were received, i.e. not only kept in Sent or Drafts.
    A mail sent from here to this account (to oneself, or to a catch-all of
    one's own domain) is identical to Roundcube's Sent copy; that copy does
    not mean the mail has arrived."""
    return {email_id: item for email_id, item in copies.items()
            if any(JMAP.mailbox_role_of(session, user, box) not in OUTGOING_ROLES
                   for box in (item.get("mailboxIds") or {}))}


def deliver(request):
    route = route_for_account(request.account)
    raw = ensure_message_id(request.raw)
    user = route.stalwart_user

    def work(session):
        same_id, identical = same_mail_copies(session, user, raw)
        # Sent and Drafts copies are never "already here", never moved.
        identical = received_copies(session, user, identical)

        # inbound_sieve.folders: INBOX, and/or Junk = the provider folder
        # with the junk role (its mark, or folders.yaml).
        filtered = ((request.mailbox.upper() == "INBOX" and "inbox" in route.sieve_folders)
                    or (request.role == "junk" and "junk" in route.sieve_folders))
        if filtered:
            set_aside = {}
            for email_id, item in sorted(identical.items()):
                roles = {JMAP.mailbox_role_of(session, user, box) for box in (item.get("mailboxIds") or {})}
                if roles and roles <= set(EXCLUSIVE_ROLES):
                    set_aside[email_id] = roles
            if request.mailbox.upper() == "INBOX" and identical and len(set_aside) == len(identical):
                # "Not spam" (Junk -> INBOX) or restored from the trash at the
                # provider: the same here; a spam verdict sticks (resieve
                # honours $notjunk).
                inbox = JMAP.resolve_mailbox(session, user, "INBOX", "", request.delimiter)
                email_id = sorted(set_aside)[0]
                patch = {"mailboxIds": {inbox: True}}
                if "junk" in set_aside[email_id]:
                    patch.update({"keywords/$notjunk": True, "keywords/$junk": None})
                JMAP.set_mailboxes(session, user, email_id, patch)
                method = "not-spam" if "junk" in set_aside[email_id] else "move"
                return DeliveryResult(method=method, account_id=session.account_id, email_id=email_id)
            if not identical:
                junk = request.role == "junk"
                deliver_smtp(raw, request.sender, route.address, junk=junk)
                return DeliveryResult(method="smtp-junk" if junk else "smtp")
            if request.role != "junk":
                # Already here (an earlier attempt, or the provider moved it
                # back into INBOX): nothing to deliver.
                return DeliveryResult(method="skip", account_id=session.account_id,
                                      email_id=sorted(identical)[0])
            # Marked as spam at the provider after it was fetched (found with
            # a test mailbox): a move into Junk, below, not a skip.

        target = JMAP.resolve_mailbox(session, user, request.mailbox, request.role,
                                      request.delimiter)
        protected = provenance_protected(request.account, set(identical))

        if JMAP.mailbox_role_of(session, user, target) == "sent" and any(
            target in (item.get("mailboxIds") or {}) for item in same_id.values()
        ):
            # The provider's own copy of a mail sent from here: ours stays.
            return DeliveryResult(method="skip-sent", account_id=session.account_id,
                                  email_id=sorted(same_id)[0])

        target_role = JMAP.mailbox_role_of(session, user, target)
        for email_id, item in sorted(identical.items()):
            roles = {JMAP.mailbox_role_of(session, user, box) for box in (item.get("mailboxIds") or {})}
            if target in (item.get("mailboxIds") or {}):
                method = "retry"            # an earlier attempt imported it
            elif target_role in EXCLUSIVE_ROLES or (roles and roles <= set(EXCLUSIVE_ROLES)):
                # Into or out of spam or trash at the provider: a move, also
                # with labels and also for mail a human placed here (marking
                # spam or deleting there is the newer human decision).
                patch = {"mailboxIds": {target: True}}
                if target_role == "junk":
                    patch.update({"keywords/$junk": True, "keywords/$notjunk": None})
                elif "junk" in roles:
                    patch.update({"keywords/$notjunk": True, "keywords/$junk": None})
                JMAP.set_mailboxes(session, user, email_id, patch)
                method = "move"
            elif email_id in protected or request.labels or target_role in OUTGOING_ROLES:
                # One mail, one more folder: placed by a human already, or a
                # label (Gmail), or the provider's Sent copy of a mail that
                # also arrived here (sent to oneself from another client).
                JMAP.set_mailboxes(session, user, email_id, {f"mailboxIds/{target}": True})
                method = "add-folder"
            else:
                # Moved at the provider after it was fetched: move it here too.
                JMAP.set_mailboxes(session, user, email_id, {"mailboxIds": {target: True}})
                method = "move"
            protect_provider_placement(request.account, email_id)
            return DeliveryResult(method=method, account_id=session.account_id, email_id=email_id)

        email_id = JMAP.import_new(raw, target, session, user)
        protect_provider_placement(request.account, email_id)
        return DeliveryResult(method="jmap", account_id=session.account_id, email_id=email_id)

    try:
        return JMAP.with_session(user, work)
    except (RuntimeError, JmapError) as exc:
        # Most often a folder made or deleted outside the bridge since its
        # list was read: once more with the list read again (the duplicate
        # check makes a repeated attempt harmless); a second failure is
        # reported to getmail, which keeps the mail and tries again later.
        print(f"bridge: {request.account}: {exc}; once more with the folder list read again", flush=True)
        JMAP.forget_mailboxes(user)
        return JMAP.with_session(user, work)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            request = read_delivery_request(self.rfile)
            result = deliver(request)

            details = (
                f"DELIVERED account={request.account!r} "
                f"mailbox={request.mailbox!r} "
                f"bytes={len(request.raw)} "
                f"via={result.method}"
            )

            if result.email_id:
                details += (
                    f" jmap_account={result.account_id} "
                    f"email_id={result.email_id}"
                )

            print(details, flush=True)
            self.wfile.write(b"OK\n")
            self.wfile.flush()

        except Exception as exc:
            print(
                f"ERROR {type(exc).__name__}: {exc}",
                flush=True,
            )

            try:
                self.wfile.write(b"ERROR\n")
                self.wfile.flush()
            except Exception:
                pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    # Non-daemon workers: server_close() (on leaving the with-block) waits
    # for in-flight deliveries instead of abandoning them at exit.
    daemon_threads = False


if __name__ == "__main__":
    with Server(
        ("0.0.0.0", LISTEN_PORT),
        Handler,
    ) as server:
        # As PID 1 in its container this process ignores SIGTERM unless it
        # handles it, and `docker stop` then kills it after its timeout.
        # shutdown() blocks until serve_forever() returns, which runs in
        # this thread, so it is called from a helper thread.
        def request_shutdown(signum, frame):
            print(
                "mail bridge: SIGTERM, finishing in-flight deliveries",
                flush=True,
            )
            threading.Thread(
                target=server.shutdown,
                daemon=True,
            ).start()

        signal.signal(signal.SIGTERM, request_shutdown)

        print(
            f"mail bridge listening on :{LISTEN_PORT}",
            flush=True,
        )
        server.serve_forever()

    print("mail bridge: stopped", flush=True)
