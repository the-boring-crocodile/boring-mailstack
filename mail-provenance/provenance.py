#!/usr/bin/env python3

import base64
import imaplib
import json
import os
import re
import signal
import sqlite3
import ssl
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DB_PATH = Path("/data/provenance.sqlite")
ACCOUNTS_PATH = Path("/config/stalwart-accounts.json")
IMAP_HOST = "stalwart.mailstack.local"
IMAP_PORT = 993
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8080
BOOTSTRAP_TIMEOUT = 10.0
# resieve-watch's re-sort endpoint: a human move into INBOX (or Junk) hands
# the mail back to the filter (compose sets it; required at start).
RESORT_URL = os.environ.get("RESIEVE_WATCH_URL", "")

SCHEMA = """
CREATE TABLE IF NOT EXISTS protected_email (
    account TEXT NOT NULL,
    email_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (account, email_id)
);
"""

OBJECTID_RE = re.compile(rb"EMAILID ([^ )]+)")
LIST_MAILBOX_RE = re.compile(rb'^\([^)]*\) (?:"(?:[^"\\]|\\.)*"|NIL) (?:"((?:[^"\\]|\\.)*)"|([^ "(){}]+))$')

# The same codec lives in getmail/folders.py and demo/seed/render.py:
# separate images.
# IMAP transmits mailbox names in modified UTF-7 (RFC 3501 §5.1.3), while
# Stalwart telemetry reports them in UTF-8. Names are kept in UTF-8 here
# and encoded only on the wire; otherwise a folder such as "Entwürfe" never
# matches its telemetry (bootstrap then times out) and moves into it cannot
# be resolved.
def mutf7_encode(name):
    out, pending = [], []

    def flush():
        if pending:
            raw = "".join(pending).encode("utf-16-be")
            out.append("&" + base64.b64encode(raw).decode().rstrip("=").replace("/", ",") + "-")
            pending.clear()

    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            pending.append(ch)
    flush()
    return "".join(out)


def mutf7_decode(name):
    out, i = [], 0
    while i < len(name):
        if name[i] != "&":
            out.append(name[i])
            i += 1
            continue
        end = name.index("-", i)
        if end == i + 1:
            out.append("&")
        else:
            chunk = name[i + 1:end].replace(",", "/")
            chunk += "=" * (-len(chunk) % 4)
            out.append(base64.b64decode(chunk).decode("utf-16-be"))
        i = end + 1
    return "".join(out)


def imap_mailbox(name):
    """A UTF-8 mailbox name as a quoted IMAP argument."""
    wire = mutf7_encode(name).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{wire}"'


class TelemetryMappings:
    """Translate transient Stalwart telemetry IDs to durable identities."""

    def __init__(self, account_directory):
        self.account_directory = account_directory
        self.lock = threading.RLock()
        self.account_by_numeric_id = {}
        self.mailbox_by_numeric_id = {}

    def remember_account(self, data):
        numeric_id = data.get("accountId")
        account_name = data.get("accountName")
        account = self.account_directory.find_by_login_name(account_name)

        if numeric_id is None or account is None:
            return

        with self.lock:
            self.account_by_numeric_id[numeric_id] = account

        print(
            f'mail-provenance: account {numeric_id} -> {account["id"]}',
            flush=True,
        )

    def remember_mailbox(self, data):
        numeric_account_id = data.get("accountId")
        numeric_mailbox_id = data.get("mailboxId")
        # imap.create-mailbox reports the id as a one-element list.
        if isinstance(numeric_mailbox_id, list):
            numeric_mailbox_id = numeric_mailbox_id[0] if len(numeric_mailbox_id) == 1 else None
        mailbox_name = data.get("mailboxName")

        if (
            numeric_account_id is None
            or numeric_mailbox_id is None
            or mailbox_name is None
        ):
            return

        with self.lock:
            self.mailbox_by_numeric_id[
                (numeric_account_id, numeric_mailbox_id)
            ] = mailbox_name

        print(
            "mail-provenance: mailbox "
            f"({numeric_account_id},{numeric_mailbox_id})"
            f" -> {mailbox_name!r}",
            flush=True,
        )

    def resolve_move_destination(
        self,
        numeric_account_id,
        numeric_mailbox_id,
    ):
        with self.lock:
            account = self.account_by_numeric_id.get(
                numeric_account_id
            )
            mailbox_name = self.mailbox_by_numeric_id.get(
                (numeric_account_id, numeric_mailbox_id)
            )

        return account, mailbox_name

    def ready_for(self, expected_mailboxes):
        """Return whether every successfully examined mailbox is mapped."""

        with self.lock:
            numeric_by_account = {
                account["id"]: numeric_id
                for numeric_id, account
                in self.account_by_numeric_id.items()
            }

            mapped_mailboxes = dict(self.mailbox_by_numeric_id)

        for account_id, mailbox_names in expected_mailboxes.items():
            numeric_account_id = numeric_by_account.get(account_id)

            if numeric_account_id is None:
                return False

            observed_names = {
                mailbox_name
                for (observed_account_id, _), mailbox_name
                in mapped_mailboxes.items()
                if observed_account_id == numeric_account_id
            }

            if not mailbox_names <= observed_names:
                return False

        return True


class ProvenanceStore:
    """Durable record of mail whose human placement must be preserved."""

    def __init__(self, path):
        self.path = path

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.path) as db:
            db.executescript(SCHEMA)

    def protect(self, account_id, email_id, reason, created_at):
        with sqlite3.connect(self.path) as db:
            before = db.total_changes

            db.execute(
                """
                INSERT OR IGNORE INTO protected_email
                    (account, email_id, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    account_id,
                    email_id,
                    reason,
                    created_at,
                ),
            )

            inserted = db.total_changes != before

        if inserted:
            print(
                f"mail-provenance: protected {account_id}/{email_id}"
                f" reason={reason}",
                flush=True,
            )
        else:
            print(
                f"mail-provenance: already protected "
                f"{account_id}/{email_id}",
                flush=True,
            )

    def protected(self, account_id, email_ids):
        """The subset of email_ids recorded as placed by a human."""
        if not email_ids:
            return set()
        with sqlite3.connect(self.path) as db:
            marks = ",".join("?" * len(email_ids))
            rows = db.execute(
                f"SELECT email_id FROM protected_email WHERE account = ? AND email_id IN ({marks})",
                (account_id, *email_ids),
            ).fetchall()
        return {row[0] for row in rows}


class AccountDirectory:
    """Immutable account configuration loaded from generated config."""

    def __init__(self, accounts, by_login_name):
        self.accounts = accounts
        self.by_login_name = by_login_name

    @classmethod
    def load(cls, path):
        with path.open() as f:
            records = json.load(f)

        accounts = []
        by_login_name = {}

        for record in records:
            account = {
                "id": record["id"],
                "address": record["address"],
                "login": record["login"],
                "password": record["password"],
            }

            accounts.append(account)

            # auth.success names the login, which is the address.
            by_login_name[account["login"]] = account

        return cls(accounts, by_login_name)

    def find_by_login_name(self, name):
        return self.by_login_name.get(name)


def imap_connect(account):
    # This client talks only to Stalwart on the private Docker network.
    # Its internal certificate is not rooted in the public CA store, so
    # certificate validation is deliberately disabled for this connection.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    imap = imaplib.IMAP4_SSL(
        IMAP_HOST,
        IMAP_PORT,
        ssl_context=context,
    )

    imap.login(account["login"], account["password"])
    return imap


def list_mailboxes(imap):
    # Quoted names (with \\ and \" escapes), atoms and literals; an entry
    # that still does not parse is skipped with a log line, so one unusual
    # folder name cannot keep provenance from starting.
    typ, data = imap.list()

    if typ != "OK":
        raise RuntimeError("IMAP LIST failed")

    mailboxes = []

    for item in data:
        # A name sent as an IMAP literal arrives as (prefix, name).
        if isinstance(item, tuple) and len(item) == 2:
            mailboxes.append(mutf7_decode(item[1].decode("ascii", "replace")))
            continue
        if not isinstance(item, bytes) or item in (b")", b""):
            continue

        match = LIST_MAILBOX_RE.fullmatch(item)
        if match is None:
            # One unusual name must not stop provenance: skip it, say so.
            print(f"mail-provenance: skipping unparsable LIST entry {item!r}", flush=True)
            continue

        quoted, atom = match.group(1), match.group(2)
        name = re.sub(rb'\\(.)', rb'\1', quoted) if quoted is not None else atom
        mailboxes.append(mutf7_decode(name.decode("ascii")))

    return mailboxes


def bootstrap_account(account):
    imap = imap_connect(account)
    examined = set()

    try:
        mailboxes = list_mailboxes(imap)

        print(
            f'mail-provenance: bootstrap {account["id"]}:'
            f" {len(mailboxes)} mailboxes",
            flush=True,
        )

        for mailbox in mailboxes:
            typ, _ = imap.select(imap_mailbox(mailbox), readonly=True)

            if typ != "OK":
                raise RuntimeError(
                    f"EXAMINE failed for {account['id']}/{mailbox!r}"
                )

            examined.add(mailbox)
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return examined


def bootstrap(account_directory):
    expected_mailboxes = {}

    for account in account_directory.accounts:
        expected_mailboxes[account["id"]] = bootstrap_account(account)

    return expected_mailboxes


def wait_for_mappings(telemetry, expected_mailboxes, stopping):
    # Bootstrap EXAMINEs generate the imap.select telemetry that teaches us
    # Stalwart's transient numeric account/mailbox IDs. Startup is complete
    # only after every successfully examined mailbox has been observed.
    # A stop request ends the wait: the receiver is shutting down anyway.
    deadline = time.monotonic() + BOOTSTRAP_TIMEOUT

    while time.monotonic() < deadline:
        if stopping.is_set() or telemetry.ready_for(expected_mailboxes):
            return

        time.sleep(0.1)

    raise RuntimeError(
        "bootstrap telemetry mappings did not arrive before timeout"
    )


UID_RE = re.compile(rb"\bUID (\d+)")


def fetch_email_ids(account, mailbox_name, uids):
    """{uid: Email ID} for the given UIDs of a mailbox, over one connection.
    imap.move/copy report destination UIDs; UIDs are mailbox-local and
    transient, Stalwart's OBJECTID gives the stable JMAP Email ID. A UID that
    is gone (moved on or expunged meanwhile) is simply missing."""
    imap = imap_connect(account)
    try:
        typ, _ = imap.select(imap_mailbox(mailbox_name), readonly=True)
        if typ != "OK":
            raise RuntimeError(f"EXAMINE failed for {mailbox_name!r}")
        found = {}
        for start in range(0, len(uids), 500):
            chunk = ",".join(str(u) for u in uids[start:start + 500])
            typ, data = imap.uid("FETCH", chunk, "(UID OBJECTID)")
            if typ != "OK":
                raise RuntimeError(f"OBJECTID fetch failed for {mailbox_name!r}")
            for item in data or []:
                line = item[0] if isinstance(item, tuple) else item
                if not isinstance(line, bytes):
                    continue
                uid, match = UID_RE.search(line), OBJECTID_RE.search(line)
                if uid and match:
                    found[int(uid.group(1))] = match.group(1).decode("ascii")
        return found
    finally:
        try:
            imap.logout()
        except Exception:
            pass


class TransientError(Exception):
    """Worth Stalwart's retry: the webhook answers 500 for it (writes are
    idempotent); any other failed event is logged and skipped, so it can no
    longer hold back the events after it."""


RELEARN_INTERVAL = 60
_relearned = {}
_relearn_lock = threading.Lock()


def unknown_mapping(telemetry, account, what):
    """A mailbox (or account) we have no name for yet, e.g. a folder made
    over JMAP and never selected over IMAP. Examine the account's folders
    (or log every account in) so Stalwart reports the mapping, then ask for
    a retry. At most once a minute per account."""
    key = account["id"] if account is not None else "*"
    with _relearn_lock:
        due = time.monotonic() - _relearned.get(key, -RELEARN_INTERVAL) >= RELEARN_INTERVAL
        if due:
            _relearned[key] = time.monotonic()
    if due:
        for each in ([account] if account is not None else telemetry.account_directory.accounts):
            try:
                bootstrap_account(each)
            except Exception as exc:
                print(f"mail-provenance: relearning {each['id']} failed: {exc}", flush=True)
    raise TransientError(f"{what}; mapping requested, retry")


def fetch_email_ids_by_message_id(account, mailbox_name, message_id, recent=200):
    """Email IDs of the newest mails in a mailbox whose Message-ID matches
    (an APPEND reports Stalwart's documentId and the Message-ID, not a UID)."""
    imap = imap_connect(account)
    try:
        typ, data = imap.select(imap_mailbox(mailbox_name), readonly=True)
        if typ != "OK":
            raise TransientError(f"EXAMINE failed for {mailbox_name!r}")
        typ, data = imap.uid("SEARCH", None, "ALL")
        uids = data[0].split() if typ == "OK" and data and data[0] else []
        if not uids:
            return []
        wanted = message_id.strip().strip("<>").encode()
        typ, data = imap.uid(
            "FETCH",
            b",".join(uids[-recent:]).decode(),
            "(UID OBJECTID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])",
        )
        found = []
        for item in data:
            if not isinstance(item, tuple):
                continue
            header = item[1].split(b":", 1)[-1].strip().strip(b"<>")
            match = OBJECTID_RE.search(item[0])
            if match and header == wanted:
                found.append(match.group(1).decode("ascii"))
        return found
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def handle_append(telemetry, store, event):
    data = event.get("data", {})
    mailbox_ids = data.get("mailboxId")
    mailbox_ids = mailbox_ids if isinstance(mailbox_ids, list) else [mailbox_ids]
    message_id = data.get("messageId")
    if not message_id:
        raise RuntimeError("APPEND without Message-ID; cannot identify the mail")
    for mailbox_id in mailbox_ids:
        account, mailbox_name = telemetry.resolve_move_destination(data.get("accountId"), mailbox_id)
        if account is None or mailbox_name is None:
            unknown_mapping(telemetry, account, f"APPEND into unknown mailbox ({data.get('accountId')},{mailbox_id})")
        ids = fetch_email_ids_by_message_id(account, mailbox_name, message_id)
        if not ids:
            # Retried until the webhook's discardAfter (6 h) gives up.
            raise TransientError(f"APPEND into {mailbox_name!r}: mail not found by Message-ID yet")
        for email_id in ids:
            store.protect(account["id"], email_id, "imap-append",
                          event.get("createdAt") or datetime.now(timezone.utc).isoformat())


def handle_move(telemetry, store, event, reason="imap-move"):
    data = event.get("data", {})

    account_id = data.get("accountId")
    mailbox_id = data.get("mailboxId")
    destination_uids = data.get("uid") or []

    account, mailbox_name = telemetry.resolve_move_destination(
        account_id,
        mailbox_id,
    )

    if account is None or mailbox_name is None:
        unknown_mapping(telemetry, account, f"unknown mailbox ({account_id},{mailbox_id})")

    # One connection for the whole move; a UID that is gone meanwhile is
    # skipped, the others are still recorded (and handed to the filter).
    email_ids = fetch_email_ids(account, mailbox_name, [int(u) for u in destination_uids])
    moved = []
    for uid in destination_uids:
        email_id = email_ids.get(int(uid))
        if email_id is None:
            print(f"mail-provenance: {mailbox_name!r} UID {uid} is gone; skipped", flush=True)
            continue

        store.protect(
            account["id"],
            email_id,
            reason,
            event.get("createdAt")
            or datetime.now(timezone.utc).isoformat(),
        )
        moved.append(email_id)

    # Re-sort chute: moved into INBOX or Junk, the mail goes back to the
    # filter. resieve decides (Junk only when it may sort Junk) and releases
    # the record; until then the mail stays protected.
    if moved and (mailbox_name.upper() == "INBOX" or mailbox_name == junk_folder(account)):
        notify_resort(account["id"], moved)


_junk_names = {}


def junk_folder(account):
    """The account's Junk folder name (IMAP special-use \\Junk), cached."""
    cached = _junk_names.get(account["id"])
    if cached and time.monotonic() - cached[0] < 600:
        return cached[1]
    name = None
    imap = imap_connect(account)
    try:
        typ, data = imap.list()
        for item in data or []:
            if isinstance(item, bytes) and b"\\Junk" in item:
                match = LIST_MAILBOX_RE.fullmatch(item)
                if match:
                    raw = match.group(1) if match.group(1) is not None else match.group(2)
                    name = mutf7_decode(re.sub(rb'\\(.)', rb'\1', raw).decode("ascii"))
                break
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    _junk_names[account["id"]] = (time.monotonic(), name)
    return name


def notify_resort(account_id, email_ids):
    request = urllib.request.Request(
        RESORT_URL,
        data=json.dumps({"account": account_id, "email_ids": email_ids}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except OSError as exc:
        # The whole event is retried (recording is idempotent), so the
        # hand-back is not lost while resieve-watch is away.
        raise TransientError(f"re-sort request failed ({exc})")
    print(f"mail-provenance: {account_id}: {len(email_ids)} mail(s) handed back to the filter", flush=True)


MAPPING_EVENTS = {"auth.success", "imap.select", "imap.append",
                  "imap.create-mailbox", "imap.rename-mailbox"}


def handle_event(telemetry, store, event):
    event_type = event.get("type")
    data = event.get("data", {})

    if event_type == "auth.success":
        telemetry.remember_account(data)
    elif event_type in MAPPING_EVENTS:
        telemetry.remember_mailbox(data)
    elif event_type == "imap.move":
        handle_move(telemetry, store, event)
    elif event_type == "imap.copy":
        handle_move(telemetry, store, event, reason="imap-copy")
    elif event_type == "message-ingest.imap-append":
        handle_append(telemetry, store, event)


def handle_events(telemetry, store, events):
    """Mappings first (an APPEND's mailbox name arrives in the batch after
    it), then each event on its own. Returns whether a transient failure
    asks for Stalwart's retry."""
    retry = False
    ordered = ([e for e in events if e.get("type") in MAPPING_EVENTS]
               + [e for e in events if e.get("type") not in MAPPING_EVENTS])
    for event in ordered:
        try:
            handle_event(telemetry, store, event)
        except (OSError, imaplib.IMAP4.error, sqlite3.OperationalError, TransientError) as exc:
            # A refused login too: after a password change the services
            # restart with the new one (DEPLOY.md: down, then up -d).
            retry = True
            print(f"mail-provenance: {event.get('type')}: {type(exc).__name__}: {exc} (retried)", flush=True)
        except Exception as exc:
            print(f"mail-provenance: {event.get('type')}: {exc} (not recorded; cannot be retried)", flush=True)
    return retry


class WebhookServer(ThreadingHTTPServer):
    """HTTP server carrying the application dependencies for handlers."""

    # Non-daemon workers: server_close() waits for in-flight webhooks, so a
    # stop never cuts a provenance write short.
    daemon_threads = False

    def __init__(self, address, telemetry, store):
        super().__init__(address, WebhookHandler)
        self.telemetry = telemetry
        self.store = store


class WebhookHandler(BaseHTTPRequestHandler):
    # A 2xx response acknowledges the complete request. Writes are idempotent:
    # ProvenanceStore.protect() uses INSERT OR IGNORE.
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))

            if self.path == "/protected":
                # Which of these mails are placed by a human (bridge lookup).
                account = payload["account"]
                ids = payload["email_ids"]
                if not (isinstance(account, str) and account and isinstance(ids, list)
                        and len(ids) <= 1000 and all(isinstance(i, str) and i for i in ids)):
                    raise ValueError("invalid lookup request")
                body = json.dumps({"protected": sorted(self.server.store.protected(account, ids))}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/protect":
                account = payload["account"]
                email_id = payload["email_id"]
                reason = payload["reason"]

                if not all(
                    isinstance(value, str) and value
                    for value in (account, email_id, reason)
                ):
                    raise ValueError("invalid protection request")

                self.server.store.protect(
                    account,
                    email_id,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                )
            elif self.path in ("/", "/webhook"):
                if handle_events(self.server.telemetry, self.server.store,
                                 payload.get("events", [])):
                    raise TransientError("an event failed transiently; Stalwart retries the batch")
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"NOT FOUND\n")
                return

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK\n")

        except Exception as exc:
            print(
                f"mail-provenance: webhook failed: {exc}",
                flush=True,
            )
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"ERROR\n")

    def log_message(self, format, *args):
        return


def main():
    if not RESORT_URL:
        raise SystemExit("mail-provenance: RESIEVE_WATCH_URL is not set (compose sets it)")
    account_directory = AccountDirectory.load(ACCOUNTS_PATH)
    telemetry = TelemetryMappings(account_directory)
    store = ProvenanceStore(DB_PATH)
    store.initialize()

    print(
        f"mail-provenance: loaded {len(account_directory.accounts)} accounts",
        flush=True,
    )
    print(
        f"mail-provenance: database ready: {DB_PATH}",
        flush=True,
    )

    server = WebhookServer(
        (LISTEN_HOST, LISTEN_PORT),
        telemetry,
        store,
    )

    print(
        f"mail-provenance: listening on {LISTEN_HOST}:{LISTEN_PORT}",
        flush=True,
    )

    server_thread = threading.Thread(
        target=server.serve_forever,
        name="webhook",
        daemon=True,
    )

    # As PID 1 in its container this process ignores SIGTERM unless it
    # handles it, and `docker stop` then kills it after its timeout.
    stopping = threading.Event()

    def request_shutdown(signum, frame):
        if stopping.is_set():
            return
        stopping.set()
        print(
            "mail-provenance: SIGTERM, finishing in-flight webhooks",
            flush=True,
        )
        # shutdown() blocks until serve_forever() returns; never call it
        # from the signal handler's own thread.
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    # Start the receiver before bootstrap: the bootstrap IMAP logins and
    # EXAMINEs deliberately generate auth.success/imap.select telemetry, and
    # that telemetry is how transient Stalwart IDs are learned.
    server_thread.start()

    expected_mailboxes = bootstrap(account_directory)
    wait_for_mappings(telemetry, expected_mailboxes, stopping)

    if not stopping.is_set():
        print(
            "mail-provenance: bootstrap complete",
            flush=True,
        )

    server_thread.join()
    server.server_close()

    print("mail-provenance: stopped", flush=True)


if __name__ == "__main__":
    main()
