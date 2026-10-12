#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from accounts_yaml import (
    folder_rules, inbound_sieve_folders, resieve_enabled, resieve_never_move_from, yaml_error,
)


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "accounts.yaml"
FOLDERS = ROOT / "folders.yaml"
SYNTAX_CHECK = ROOT / "tools" / "check-account-syntax.py"
OUTPUT = ROOT / "generated"


def die(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def write_private(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def curl_quote(value):
    """A value in curl's config file syntax (double quotes, backslash escapes)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def generate_getmail(account_id, account, target, folders):
    cfg = account["inbound"]

    if not cfg["active"]:
        return

    getmail_dir = target / "getmail"
    getmail_dir.mkdir(mode=0o700, exist_ok=True)

    content = f"""[retriever]
type = SimpleIMAPSSLRetriever
server = {cfg["host"]}
port = {cfg["port"]}
# Verify the provider: without ca_certs getmail (6.x, via imaplib) checks
# neither the certificate chain nor the host name.
ca_certs = /etc/ssl/certs/ca-certificates.crt
username = {cfg["username"]}
password = {cfg["password"]}
# ALL: the image's folders.py replaces it by the provider's folder list
# without views and without what folders.yaml skips.
mailboxes = ALL

[destination]
type = MDA_external
path = /app/handoff.py
allow_root_commands = true
arguments = ("{account_id}", "%(mailbox)", "%(sender)")

[options]
delete = false
read_all = false
"""

    write_private(
        getmail_dir / f"{account_id}.conf",
        content,
    )
    # The folder scan (getmail/entrypoint.sh): curl reads the provider's
    # address and login from this file, never from its command line.
    url = "imaps://%s:%s/" % (cfg["host"], cfg["port"])
    login = cfg["username"] + ":" + cfg["password"]
    write_private(
        getmail_dir / f"{account_id}.curl",
        f"url = {curl_quote(url)}\nuser = {curl_quote(login)}\n",
    )
    # The image's folders.py: what each provider folder is (folders.yaml).
    write_private(
        getmail_dir / f"{account_id}.folders.json",
        json.dumps(folder_rules(folders, account_id, cfg["host"])) + "\n",
    )


def generate_routes(accounts, target):
    routes = {}

    for account_id, account in accounts.items():
        routes[account_id] = {
            "address": account["address"],
            "active": account["inbound"]["active"],
            # The Stalwart account is the real address (DECISIONS.md).
            "stalwart_user": account["address"],
            # Provider folders whose mail goes through the filter (SMTP);
            # every other folder is imported as it is.
            "sieve_folders": inbound_sieve_folders(account),
        }

    write_private(
        target / "bridge-routes.json",
        json.dumps(routes, indent=2, sort_keys=True) + "\n",
    )



def generate_stalwart_accounts(accounts, target):
    desired = []

    for account_id, account in accounts.items():
        if not account["inbound"]["active"]:
            continue

        address = account["address"]
        local, domain = address.rsplit("@", 1)

        desired.append({
            # Our key (accounts.yaml), used for provenance and state files.
            "id": account_id,
            "address": address,
            # The Stalwart account: the real address. Logins (Roundcube,
            # bridge, resieve, provenance) use it.
            "login": address,
            "local": local,
            "domain": domain,
            "description": address,
            "password": account["inbound"]["password"],
            # resieve-watch: resieve --apply after a filter change (opt-out).
            "resieve_enabled": resieve_enabled(account),
        })
        # resieve never takes mail out of these (roles or paths); absent:
        # resieve's default (Sent, Drafts, Trash, Junk).
        never = resieve_never_move_from(account)
        if never is not None:
            desired[-1]["resieve_protected_folders"] = never

    write_private(
        target / "stalwart-accounts.json",
        json.dumps(desired, indent=2, sort_keys=True) + "\n",
    )


def generate_postfix(accounts, target):
    postfix_dir = target / "postfix"
    postfix_dir.mkdir(mode=0o700, exist_ok=True)

    sender_relay = []
    sasl_passwd = []
    sender_access = []

    for account_id, account in accounts.items():
        cfg = account["outbound"]

        if not cfg["active"]:
            continue

        address = account["address"]
        relay = f'[{cfg["host"]}]:{cfg["port"]}'

        sender_relay.append(
            f"{address}\t{relay}"
        )

        # With smtp_sender_dependent_authentication=yes Postfix first
        # looks up SASL credentials by envelope sender. This deliberately
        # keeps credentials independent even when accounts share a relay.
        sasl_passwd.append(
            f'{address}\t{cfg["username"]}:{cfg["password"]}'
        )

        sender_access.append(
            f"{address}\tOK"
        )

    write_private(
        postfix_dir / "sender_relay",
        "\n".join(sender_relay) + ("\n" if sender_relay else ""),
    )

    write_private(
        postfix_dir / "sasl_passwd",
        "\n".join(sasl_passwd) + ("\n" if sasl_passwd else ""),
    )

    write_private(
        postfix_dir / "sender_access",
        "\n".join(sender_access) + ("\n" if sender_access else ""),
    )

    # relay/entrypoint.sh narrows inet_interfaces and sets mynetworks at start: they
    # depend on the container's addresses, known only there.
    main_cf = f"""# Generated by mailstack. Do not edit.
compatibility_level = 3.6

# This instance is an internal provider relay, not an Internet MX.
inet_interfaces = all
mydestination =
relayhost =

# The stack's message limit (stack.env), as Stalwart's.
message_size_limit = {os.environ["MAILSTACK_MAX_MESSAGE_BYTES"]}

# The container entrypoint derives mynetworks from its attached Docker network.

# Accept only explicitly configured outbound-active envelope senders.
# Evaluate this at MAIL FROM rather than delaying it until RCPT TO.
smtpd_delay_reject = no
smtpd_sender_restrictions =
    check_sender_access texthash:/etc/postfix/generated/sender_access
    reject

# Route and authenticate independently by envelope sender.
sender_dependent_relayhost_maps = texthash:/etc/postfix/generated/sender_relay
smtp_sender_dependent_authentication = yes
smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = texthash:/etc/postfix/generated/sasl_passwd
smtp_sasl_security_options = noanonymous

# Current configured providers use implicit TLS submission on port 465.
# Require both encryption and verification of the provider certificate.
smtp_tls_wrappermode = yes
smtp_tls_security_level = verify
smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt

# Send Postfix logging to the container log stream.
maillog_file = /dev/stdout
"""
    write_private(
        postfix_dir / "main.cf",
        main_cf,
    )


def main():
    result = subprocess.run(
        [str(SYNTAX_CHECK)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout, end="", file=sys.stderr)
        die("accounts.yaml validation failed")

    try:
        with CONFIG.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        die(yaml_error(CONFIG, exc))

    accounts = data["accounts"]
    with FOLDERS.open("r", encoding="utf-8") as f:
        folders = yaml.safe_load(f)

    OUTPUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    OUTPUT.chmod(0o700)

    temp_parent = Path(
        tempfile.mkdtemp(
            prefix=".next-",
            dir=OUTPUT,
        )
    )

    try:
        temp_parent.chmod(0o700)

        for account_id, account in accounts.items():
            generate_getmail(account_id, account, temp_parent, folders)

        generate_routes(accounts, temp_parent)
        generate_stalwart_accounts(accounts, temp_parent)
        generate_postfix(accounts, temp_parent)

        # Generation above must complete successfully before we touch the
        # currently usable configuration. Consumers start only after this
        # init job succeeds, so committing the top-level artifacts here is
        # sufficient while keeping OUTPUT itself a stable bind mount.
        generated_names = {item.name for item in temp_parent.iterdir()}

        for existing in OUTPUT.iterdir():
            if existing == temp_parent or existing.name.startswith(".next-"):
                continue
            if existing.name not in generated_names:
                if existing.is_dir() and not existing.is_symlink():
                    shutil.rmtree(existing)
                else:
                    existing.unlink()

        for item in temp_parent.iterdir():
            target = OUTPUT / item.name

            if item.is_dir() and not item.is_symlink():
                # Preserve generated subdirectory inodes because consumers
                # may have them bind-mounted. Replace their contents, not
                # the directories themselves.
                target.mkdir(mode=0o700, exist_ok=True)
                target.chmod(0o700)

                incoming_names = {child.name for child in item.iterdir()}

                for existing in target.iterdir():
                    if existing.name not in incoming_names:
                        if existing.is_dir() and not existing.is_symlink():
                            shutil.rmtree(existing)
                        else:
                            existing.unlink()

                for child in item.iterdir():
                    destination = target / child.name

                    if destination.exists() or destination.is_symlink():
                        if destination.is_dir() and not destination.is_symlink():
                            shutil.rmtree(destination)
                        else:
                            destination.unlink()

                    os.replace(child, destination)

                item.rmdir()
                continue

            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()

            os.replace(item, target)

    finally:
        if temp_parent.exists():
            shutil.rmtree(temp_parent)

    print("OK: configuration generated")
    print(f"  output: {OUTPUT}")

    active = [
        account_id
        for account_id, account in accounts.items()
        if account["inbound"]["active"]
    ]

    print(
        "  inbound: "
        + (", ".join(active) if active else "(none)")
    )

    outbound = [
        account_id
        for account_id, account in accounts.items()
        if account["outbound"]["active"]
    ]

    print(
        "  outbound: "
        + (", ".join(outbound) if outbound else "(none)")
    )


if __name__ == "__main__":
    main()
