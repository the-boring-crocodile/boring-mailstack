#!/usr/bin/env python3

import re
import sys
import unicodedata
from pathlib import Path

import yaml

from accounts_yaml import folder_rules_errors, yaml_error


CONFIG = Path(__file__).resolve().parent.parent / "accounts.yaml"
FOLDERS = CONFIG.with_name("folders.yaml")

ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
# Names of the stack's own Stalwart accounts and of system mailboxes.
RESERVED_IDS = {"admin", "mail-bridge", "mail-relay", "relay", "postmaster", "root", "abuse"}
PLACEHOLDERS = {"", "CHANGE-ME", "CHANGE_ME", "TO_BE_CONFIRMED"}   # CHANGE-ME: accounts.example.yaml

TOP_KEYS = {"version", "accounts"}
ACCOUNT_KEYS = {"address", "inbound", "outbound"}
OPTIONAL_ACCOUNT_KEYS = {"inbound_sieve", "resieve"}
INBOUND_SIEVE_KEYS = {"enabled", "folders"}
RESIEVE_KEYS = {"enabled", "never_move_from"}
INBOUND_KEYS = {
    "active", "host", "port", "tls",
    "username", "password",
}
OUTBOUND_KEYS = {
    "active", "host", "port", "tls",
    "username", "password",
}
TLS_VALUES = {"implicit"}


def fail(message):
    raise ValueError(message)


def require_mapping(value, where):
    if not isinstance(value, dict):
        fail(f"{where}: expected mapping")


def check_keys(data, allowed, where):
    unknown = set(data) - allowed
    if unknown:
        fail(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")


def require_fields(data, fields, where):
    missing = fields - set(data)
    if missing:
        fail(f"{where}: missing field(s): {', '.join(sorted(missing))}")


def require_config_string(value, where):
    if not isinstance(value, str):
        fail(f"{where}: expected string")
    if any(unicodedata.category(char) == "Cc" for char in value):
        fail(f"{where}: control characters are not allowed")


def validate_direction(account_id, name, cfg, allowed_keys):
    where = f"accounts.{account_id}.{name}"

    require_mapping(cfg, where)
    check_keys(cfg, allowed_keys, where)

    required = {"active", "host", "port", "tls", "username", "password"}

    require_fields(cfg, required, where)

    if not isinstance(cfg["active"], bool):
        fail(f"{where}.active: expected true or false")

    if not isinstance(cfg["port"], int) or not 1 <= cfg["port"] <= 65535:
        fail(f"{where}.port: invalid TCP port")

    if not isinstance(cfg["tls"], str) or cfg["tls"] not in TLS_VALUES:
        fail(
            f"{where}.tls: unsupported value; "
            f"supported: {', '.join(sorted(TLS_VALUES))}"
        )

    for field in ("host", "username", "password"):
        require_config_string(cfg[field], f"{where}.{field}")

    for field in ("username", "password"):
        if cfg[field] != cfg[field].strip():
            fail(f"{where}.{field}: leading or trailing whitespace is not allowed")

    if ":" in cfg["username"]:
        # Postfix's sasl_passwd and curl's user option both split user:password
        # at the first colon.
        fail(f"{where}.username: colon is not allowed")

    if cfg["active"]:
        for field in ("host", "username", "password"):
            if cfg[field].strip() in PLACEHOLDERS:
                fail(f"{where}.{field}: active direction contains placeholder")



def folder_list(value, where, commas_ok=True):
    if not isinstance(value, list) or not all(
        isinstance(f, str) and f.strip() and (commas_ok or "," not in f)
        and not any(ord(c) < 32 or ord(c) == 127 for c in f)
        for f in value
    ):
        fail(f"{where}: expected a list of folder names"
             + ("" if commas_ok else ", without commas"))


def validate_inbound_sieve(cfg, where):
    if cfg is None:
        return
    require_mapping(cfg, where)
    check_keys(cfg, INBOUND_SIEVE_KEYS, where)
    if not isinstance(cfg.get("enabled", True), bool):
        fail(f"{where}.enabled: expected true or false")
    if "folders" in cfg:
        folder_list(cfg["folders"], f"{where}.folders")
        other = [f for f in cfg["folders"] if f.casefold() not in ("inbox", "junk")]
        if other:
            fail(f"{where}.folders: only INBOX and Junk (the provider's spam folder, "
                 f"by its role in folders.yaml or its mark), not {other[0]!r}")


def validate_resieve(cfg, where):
    if cfg is None:
        return
    require_mapping(cfg, where)
    check_keys(cfg, RESIEVE_KEYS, where)
    if not isinstance(cfg.get("enabled", True), bool):
        fail(f"{where}.enabled: expected true or false")
    if "never_move_from" in cfg:
        folder_list(cfg["never_move_from"], f"{where}.never_move_from", commas_ok=False)


def validate(data):
    require_mapping(data, "root")
    check_keys(data, TOP_KEYS, "root")
    require_fields(data, TOP_KEYS, "root")

    if data["version"] != 1:
        fail("version: expected 1")

    accounts = data["accounts"]
    require_mapping(accounts, "accounts")

    if not accounts:
        fail("accounts: no accounts configured")

    addresses = set()

    for account_id, account in accounts.items():
        if not isinstance(account_id, str) or not ID_RE.fullmatch(account_id):
            fail("accounts: invalid account id")
        if account_id in RESERVED_IDS:
            fail(f"accounts.{account_id}: reserved account id; choose another")

        where = f"accounts.{account_id}"
        require_mapping(account, where)
        check_keys(account, ACCOUNT_KEYS | OPTIONAL_ACCOUNT_KEYS, where)
        require_fields(account, ACCOUNT_KEYS, where)
        validate_inbound_sieve(account.get("inbound_sieve"), f"{where}.inbound_sieve")
        validate_resieve(account.get("resieve"), f"{where}.resieve")

        address = account["address"]
        require_config_string(address, f"{where}.address")
        local, at, domain = address.rpartition("@")
        if not at or not local or not domain or "@" in local or " " in address:
            fail(f"{where}.address: invalid mail address (one @, something before and after it)")

        normalized = address.lower()
        if normalized in addresses:
            fail(f"{where}.address: duplicate address")
        addresses.add(normalized)

        validate_direction(
            account_id, "inbound", account["inbound"], INBOUND_KEYS
        )
        validate_direction(
            account_id, "outbound", account["outbound"], OUTBOUND_KEYS
        )

    return accounts


def main():
    try:
        with CONFIG.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        accounts = validate(data)

        try:
            with FOLDERS.open("r", encoding="utf-8") as f:
                folders = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(f"ERROR: {yaml_error(FOLDERS, exc)}", file=sys.stderr)
            return 1
        errors = folder_rules_errors(folders, set(accounts))
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1

    except yaml.YAMLError as exc:
        print(f"ERROR: {yaml_error(CONFIG, exc)}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {len(accounts)} account(s) validated")

    for account_id, account in accounts.items():
        inbound = "active" if account["inbound"]["active"] else "inactive"
        outbound = "active" if account["outbound"]["active"] else "inactive"

        print(
            f"  {account_id:<10} "
            f"{account['address']:<30} "
            f"in={inbound:<8} out={outbound}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
