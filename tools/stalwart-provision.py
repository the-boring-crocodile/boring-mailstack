#!/usr/bin/env python3

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DESIRED = ROOT / "generated" / "stalwart-accounts.json"
BRIDGE_ENV = ROOT / "bridge" / "bridge.env"

STALWART_CLI = "stalwart-cli"


def die(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def cli(*args, stdin=None):
    cmd = [
        STALWART_CLI,
        *args,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        input=stdin,
    )

    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        die(f"stalwart-cli failed: {' '.join(args)}")

    return result.stdout


def query(object_name, where=None, fields=None):
    args = ["query", object_name]

    if where:
        args += ["--where", where]

    if fields:
        args += ["--fields", ",".join(fields)]

    args.append("--json")

    output = cli(*args)

    rows = []
    for line in output.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    return rows


def create_object(object_name, payload):
    cli(
        "create",
        object_name,
        "--stdin",
        stdin=json.dumps(payload, separators=(",", ":")),
    )


def update_object(object_name, payload, object_id=None):
    args = ["update", object_name]
    if object_id is not None:
        args.append(object_id)
    args.append("--stdin")
    cli(*args, stdin=json.dumps(payload, separators=(",", ":")))


def find_domain(name, required=True):
    rows = query(
        "Domain",
        where=f"name={name}",
        fields=["id", "name"],
    )

    if len(rows) == 0:
        if required:
            die(f"Stalwart domain does not exist: {name}")
        return None

    if len(rows) > 1:
        die(f"multiple Stalwart domains matched: {name}")

    return rows[0]


def create_domain(name):
    payload = {
        "name": name,
        "isEnabled": True,
    }

    create_object("Domain", payload)


def set_external_domain_settings(domain_id):
    payload = {
        "isEnabled": True,
        "allowRelaying": True,
        "catchAllAddress": None,
        "dkimManagement": {"@type": "Manual"},
    }
    update_object("Domain", payload, domain_id)


def replace_credentials(account_id, password):
    """The password becomes the account's only credential (app passwords
    and API keys go)."""
    payload = {
        "credentials": {
            "0": {"@type": "Password", "secret": password},
        }
    }

    update_object("Account", payload, account_id)


def set_account_password(account_id, password):
    """Sets the account's password and keeps its other credentials: the
    provisioner's API key belongs to `admin`, users may have app passwords."""
    rows = [row for row in query("Account", fields=["id", "credentials"])
            if row.get("id") == account_id]
    if len(rows) != 1:
        die(f"Stalwart account {account_id} not found")
    credentials = rows[0].get("credentials") or {}
    keys = [key for key, value in credentials.items()
            if (value or {}).get("@type") == "Password"]
    if len(keys) > 1:
        die(f"Stalwart account {account_id} has {len(keys)} passwords")
    if keys:
        payload = {f"credentials/{keys[0]}/secret": password}
    else:
        free = next(str(n) for n in range(len(credentials) + 1) if str(n) not in credentials)
        payload = {f"credentials/{free}": {"@type": "Password", "secret": password}}
    update_object("Account", payload, account_id)


def find_account(name):
    rows = query(
        "Account",
        where=f"name={name}",
        fields=[
            "id", "name", "emailAddress", "description",
            "roles", "permissions",
        ],
    )

    if len(rows) > 1:
        die(f"multiple Stalwart accounts matched: {name}")

    return rows[0] if rows else None


def create_account(item, domain_id):
    payload = {
        "name": item["name"],
        "domainId": domain_id,
        "description": item["description"],
    }

    cli(
        "create",
        "Account/User",
        "--json",
        json.dumps(payload, separators=(",", ":")),
    )


def update_account(existing, item):
    wanted_description = item["description"]

    if existing.get("description") == wanted_description:
        return False

    cli(
        "update",
        "Account/User",
        existing["id"],
        "--field",
        f"description={wanted_description}",
    )

    return True


def bridge_password():
    """The bridge's Stalwart password, from etc/bridge.env (its login and
    addresses are fixed: compose.yaml)."""
    for line in BRIDGE_ENV.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "JMAP_PASSWORD" and value.strip():
            return value.strip()
    die("JMAP_PASSWORD missing from etc/bridge.env")


def create_bridge(domain_id, password):
    payload = {
        "name": "mail-bridge",
        "domainId": domain_id,
        "description": "Mailstack JMAP delivery bridge",
        "credentials": {
            "0": {"@type": "Password", "secret": password},
        },
        "roles": {"@type": "User"},
        "permissions": {
            "@type": "Merge",
            "enabledPermissions": {"impersonate": True},
            "disabledPermissions": {},
        },
    }

    create_object("Account/User", payload)


def get_json(object_name, object_id=None):
    args = ["get", object_name]
    if object_id:
        args.append(object_id)
    args.append("--json")
    return json.loads(cli(*args))


# Fixed values the stack's components share (release file stack.env).
JUNK_PORT = int(os.environ["MAILSTACK_JUNK_PORT"])
MAX_MESSAGE = int(os.environ["MAILSTACK_MAX_MESSAGE_BYTES"])

# Mail for local accounts arrives on 25 (bridge, provider INBOX) and on the
# junk port (bridge, the provider's Junk); both are delivered locally. The
# junk port is internal only (no host port in compose).
LOCAL_DELIVERY = f"(received_via_port == 25 || received_via_port == {JUNK_PORT}) && is_local_address(rcpt)"
JUNK_LISTENER = "smtp-provider-junk"
JUNK_TAG = "MAILSTACK_PROVIDER_JUNK"
BRIDGE_TRUSTED = "contains(dns_query('trusted-mail-bridge', 'ip'), remote_ip)"


def find_account_address(address):
    """The account whose primary address is `address` (names repeat across
    domains, so match the whole address)."""
    local = address.rsplit("@", 1)[0]
    rows = query("Account", where=f"name={local}",
                 fields=["id", "name", "emailAddress", "description"])
    rows = [r for r in rows if (r.get("emailAddress") or "").lower() == address.lower()]
    if len(rows) > 1:
        die(f"multiple Stalwart accounts with address {address}")
    return rows[0] if rows else None


def reconcile_domains(desired, apply):
    """Every account's real domain is a Stalwart domain (the provider stays
    authoritative for DNS, MX and DKIM)."""
    for domain_name in sorted({item["domain"].lower() for item in desired}):
        domain = find_domain(domain_name, required=False)
        if domain is None:
            print(f"CREATE {domain_name}  [provider domain]")
            if apply:
                create_domain(domain_name)
                domain = find_domain(domain_name)
        else:
            print(f"OK     {domain_name}")
        if apply:
            set_external_domain_settings(domain["id"])


def reconcile_accounts(desired, apply):
    """Each account is its real address."""
    for item in desired:
        address = item["address"]
        domain = find_domain(item["domain"], required=apply)
        existing = find_account_address(address)
        if existing is None:
            print(f"CREATE {address}")
            if apply:
                create_account({"name": item["local"], "description": item["description"]}, domain["id"])
            continue
        if existing.get("description") != item["description"]:
            print(f"UPDATE {address}: description")
            if apply:
                update_account(existing, item)
        else:
            print(f"OK     {address}")


def reconcile_passwords(desired, apply):
    for item in desired:
        existing = find_account_address(item["address"])
        if existing is None:
            if apply:
                die(f"{item['id']}: account missing after account provisioning")
            print(f"SET    {item['address']}: password")
            continue
        print(f"SET    {item['address']}: password")
        if apply:
            set_account_password(existing["id"], item["password"])


def reconcile_removed(desired, apply):
    """A user account this stack made (its description is its address) whose
    address is no longer in accounts.yaml, or no longer fetched, keeps its
    mail but loses its login: a random password nobody knows. Putting the
    account back sets its password again."""
    wanted = {item["address"].lower() for item in desired}
    for row in query("Account", fields=["id", "name", "emailAddress", "description"]):
        address = (row.get("emailAddress") or "").lower()
        if (not address or address in wanted or address.endswith("@mailstack.local")
                or (row.get("description") or "").lower() != address):
            continue
        print(f"LOCK   {address}: not in accounts.yaml (or not fetched); mail kept, login disabled")
        if apply:
            replace_credentials(row["id"], secrets.token_urlsafe(32))


def reconcile_admin(apply):
    """Stalwart's own administrator (made by the bootstrap, with a random
    password init does not keep) gets STALWART_ADMIN_PASSWORD from etc/.env,
    so the operator can log in to the admin page as `admin`."""
    password = os.environ.get("MAILSTACK_ADMIN_PASSWORD", "")
    if len(password) < 16:
        die("MAILSTACK_ADMIN_PASSWORD missing or shorter than 16 characters "
            "(STALWART_ADMIN_PASSWORD in etc/.env)")
    admin = find_account("admin")
    if admin is None:
        die("Stalwart has no account 'admin' (the bootstrap administrator)")
    if admin.get("roles") != {"@type": "Admin"} or admin.get("emailAddress") != "admin@mailstack.local":
        die("Stalwart account 'admin' is not the bootstrap administrator")
    print("SET    admin (Stalwart administrator): password")
    if apply:
        set_account_password(admin["id"], password)


def reconcile_bridge(password, apply):
    domain = find_domain("mailstack.local")
    bridge = find_account("mail-bridge")
    if bridge is None:
        print("CREATE mail-bridge@mailstack.local  [service account]")
        if apply:
            create_bridge(domain["id"], password)
        return
    if bridge.get("emailAddress") != "mail-bridge@mailstack.local":
        die("existing mail-bridge account has unexpected address")
    expected_roles = {"@type": "User"}
    expected_permissions = {"@type": "Merge", "enabledPermissions": {"impersonate": True}, "disabledPermissions": {}}
    if bridge.get("description") != "Mailstack JMAP delivery bridge":
        die("mail-bridge has unexpected description")
    if bridge.get("roles") != expected_roles:
        die("mail-bridge has unexpected roles")
    if bridge.get("permissions") != expected_permissions:
        die("mail-bridge has unexpected permissions")
    print("OK     mail-bridge@mailstack.local")
    print("SET    mail-bridge@mailstack.local: password")
    if apply:
        set_account_password(bridge["id"], password)


def reconcile_mta_throttles(apply):
    for object_type in ("MtaInboundThrottle", "MtaOutboundThrottle"):
        rows = query(object_type)

        for row in rows:
            object_id = row["id"]
            description = row.get("description") or object_id

            if row.get("enable") is False:
                print(f"OK     {object_type} disabled: {description}")
            else:
                print(f"UPDATE {object_type} disabled: {description}")
                if apply:
                    cli(
                        "update",
                        object_type,
                        object_id,
                        "--stdin",
                        stdin=json.dumps(
                            {"enable": False},
                            separators=(",", ":"),
                        ),
                    )



# What Stalwart's settings must be. Each run compares the listed fields
# and writes the ones that differ; fields not listed stay Stalwart's.

# Single objects: (object, what it is for, wanted fields).
SINGLETONS = [
    ("Jmap", "mailstack limits", {
        "maxConcurrentRequests": 4,
        "maxRequestSize": MAX_MESSAGE,
        "maxUploadSize": MAX_MESSAGE,
        "maxConcurrentUploads": 16,
        "maxUploadCount": 50000,
        "uploadQuota": 17179869184,
    }),
    # 600,000 requests per account per minute (Stalwart's default: 60,000):
    # resieve with full messages makes one request per mail; on a large
    # mailbox the default throttled it (DECISIONS.md "Stalwart request
    # limits"). Only authenticated clients on the stack's networks count.
    ("Http", "authenticated rate limit", {
        "rateLimitAuthenticated": {"count": 600000, "period": 60000},
    }),
    ("MtaStageData", "spam/trust policy", {
        "maxMessageSize": {"match": {}, "else": str(MAX_MESSAGE)},
        "enableSpamFilter": {
            "match": {
                # The junk port: the provider's Junk; our rule makes it spam.
                "0": {"if": f"local_port == {JUNK_PORT}", "then": "true"},
                # Port 25 from the bridge: provider INBOX, already filtered
                # by the provider (re-injected mail scores badly here).
                "1": {"if": BRIDGE_TRUSTED, "then": "false"},
            },
            "else": "is_empty(authenticated_as)",
        },
    }),
    ("SenderAuth", "outbound DKIM disabled", {
        "dkimSignDomain": {"match": {}, "else": "false"},
    }),
    ("MtaOutboundStrategy", "local delivery, everything else to the relay", {
        "connection": {"match": {}, "else": "'default'"},
        "route": {"match": {"0": {"if": LOCAL_DELIVERY, "then": "'local'"}},
                  "else": "'mailstack-relay'"},
        "schedule": {"match": {"0": {"if": "rcpt_domain == 'mailstack.local'", "then": "'local'"},
                               "1": {"if": "source == 'dsn'", "then": "'dsn'"},
                               "2": {"if": "source == 'report'", "then": "'report'"}},
                     "else": "'remote'"},
        "tls": {"match": {"0": {"if": "retry_num > 0 && last_error == 'tls'", "then": "'invalid-tls'"}},
                "else": "'default'"},
    }),
    ("MtaStageAuth", "no login on 25 and the junk port", {
        "require": {"match": {}, "else": f"local_port != 25 && local_port != {JUNK_PORT}"},
    }),
    # The bridge asks for no delivery reports (NOTIFY=NEVER): the provider
    # already accepted the mail, a bounce would be backscatter. Stalwart
    # offers DSN only to logged-in clients by default; the bridge too.
    ("MtaExtensions", "DSN for the bridge", {
        "dsn": {"match": {"0": {"if": "!is_empty(authenticated_as)", "then": "true"},
                          "1": {"if": BRIDGE_TRUSTED, "then": "true"}},
                "else": "false"},
    }),
]

WEBHOOK = {
    "allowInvalidCerts": False,
    "signatureKey": {"@type": "None"},
    "throttle": 1000,
    "timeout": 30000,
    "httpAuth": {"@type": "Unauthenticated"},
    "httpHeaders": {},
    "enable": True,
    "level": "trace",
    "eventsPolicy": "include",
}

# Objects found by one field: (object, key field, type to create, what it is
# for, wanted fields, compare). compare=False: created once, then left alone.
NAMED = [
    ("MtaRoute", "name", "MtaRoute/Relay", "outgoing mail to the Postfix relay", {
        "name": "mailstack-relay",
        "description": "Mailstack Postfix outbound relay",
        "address": "relay-private",
        "port": 25,
        "protocol": "smtp",
        "implicitTls": False,
        "allowInvalidCerts": False,
        "authUsername": None,
        "authSecret": {"@type": "None"},
    }, True),
    # The provenance sidecar, by its Compose service name. A changed URL
    # makes a new WebHook (changing an existing one's URL did not replace
    # its active sink in testing). Keyed by URL, so a webhook with an old
    # URL is left behind (none since the names settled, 2026-10-06).
    ("WebHook", "url", "WebHook", "mail-provenance: human placements", {
        **WEBHOOK,
        "url": "http://mail-provenance:8080/",
        "discardAfter": 21600000,      # undelivered events wait up to 6 h
        "lossy": False,
        "events": {name: True for name in (
            "auth.success", "imap.select", "imap.move", "imap.copy", "imap.append",
            "imap.create-mailbox", "imap.rename-mailbox", "message-ingest.imap-append")},
    }, True),
    # ManageSieve script changes (the events carry no account; the watcher
    # compares every account's active script).
    ("WebHook", "url", "WebHook", "resieve-watch: filter changes", {
        **WEBHOOK,
        "url": "http://resieve-watch:8080/",
        "discardAfter": 300000,
        "lossy": True,
        "events": {name: True for name in (
            "manage-sieve.create-script", "manage-sieve.update-script",
            "manage-sieve.delete-script", "manage-sieve.rename-script")},
    }, True),
    # The junk port: like 25 (no login, delivered locally), with the spam
    # filter on and a rule that makes mail carrying the bridge's
    # provider-junk header spam; Stalwart's junk rule then files what the
    # user's filter leaves in INBOX into Junk. The header can only make mail
    # spam, so forging it gains nothing. A new listener opens at Stalwart's
    # next start (tools/junkport.py restarts it once). Created once, never
    # compared: MAILSTACK_JUNK_PORT is fixed (stack.env); a changed port
    # would need the old listener removed by hand.
    ("NetworkListener", "name", "NetworkListener", "the junk port", {
        "name": JUNK_LISTENER,
        "bind": {f"[::]:{JUNK_PORT}": True},
        "protocol": "smtp",
        "tlsImplicit": False,
    }, False),
    ("SpamTag", "tag", "SpamTag/Score", "score of the provider-junk header", {
        "tag": JUNK_TAG,
        "score": 100.0,
    }, False),
    ("SpamRule", "name", "SpamRule/Header", "the provider filed this mail as spam", {
        "name": JUNK_TAG,
        "description": "mailstack: the provider filed this mail as spam",
        "enable": True,
        "priority": 1000,
        "condition": {
            "match": {"0": {
                "if": "name_lower == 'x-mailstack-provider-folder' && value_lower == 'junk'",
                "then": f"'{JUNK_TAG}'",
            }},
            "else": "false",
        },
    }, True),
]


def same(actual, wanted):
    return {key: actual.get(key) for key in wanted} == wanted


def reconcile_settings(apply):
    for object_name, purpose, wanted in SINGLETONS:
        if same(get_json(object_name), wanted):
            print(f"OK     {object_name}: {purpose}")
        else:
            print(f"UPDATE {object_name}: {purpose}")
            if apply:
                update_object(object_name, wanted)

    for object_name, key, create_as, purpose, wanted, compare in NAMED:
        label = f"{object_name} {wanted[key]} ({purpose})"
        rows = [row for row in query(object_name, fields=["id", key]) if row.get(key) == wanted[key]]
        if len(rows) > 1:
            die(f"several {object_name} objects with {key} {wanted[key]}")
        if not rows:
            print(f"CREATE {label}")
            if apply:
                create_object(create_as, wanted)
        elif not compare or same(get_json(object_name, rows[0]["id"]), wanted):
            print(f"OK     {label}")
        else:
            print(f"UPDATE {label}")
            if apply:
                update_object(object_name, wanted, rows[0]["id"])


def parse_args():
    if sys.argv[1:] == []:
        return False
    if sys.argv[1:] == ["--apply"]:
        return True
    die("usage: stalwart-provision.py [--apply]")


def main():
    apply = parse_args()
    if not DESIRED.is_file():
        die(f"{DESIRED} is missing (init runs generate-config.py first)")
    if not BRIDGE_ENV.is_file():
        die(f"{BRIDGE_ENV} is missing (etc/bridge.env, mounted by compose)")
    desired = json.loads(DESIRED.read_text(encoding="utf-8"))
    password = bridge_password()
    print("Mode:", "APPLY" if apply else "DRY RUN")
    reconcile_domains(desired, apply)
    reconcile_accounts(desired, apply)
    reconcile_passwords(desired, apply)
    reconcile_removed(desired, apply)
    reconcile_bridge(password, apply)
    reconcile_admin(apply)
    reconcile_mta_throttles(apply)
    reconcile_settings(apply)
    print()
    if apply:
        print("RELOAD Stalwart settings")
        cli("create", "Action/ReloadSettings")
        print("OK: Stalwart desired accounts applied and settings reloaded")
    else:
        print("DRY RUN ONLY: no Stalwart objects changed")


if __name__ == "__main__":
    main()
