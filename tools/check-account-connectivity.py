#!/usr/bin/env python3

import imaplib
import smtplib
import ssl
import sys
from pathlib import Path

import yaml

from accounts_yaml import yaml_error


CONFIG = Path(__file__).resolve().parent.parent / "accounts.yaml"


def test_imap(cfg):
    imap = imaplib.IMAP4_SSL(
        cfg["host"],
        cfg["port"],
        ssl_context=ssl.create_default_context(),
        timeout=15,
    )
    try:
        imap.login(cfg["username"], cfg["password"])
        imap.noop()
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def test_smtp(cfg):
    with smtplib.SMTP_SSL(
        cfg["host"],
        cfg["port"],
        context=ssl.create_default_context(),
        timeout=15,
    ) as smtp:
        smtp.login(cfg["username"], cfg["password"])


def main():
    try:
        with CONFIG.open("r", encoding="utf-8") as f:
            accounts = yaml.safe_load(f)["accounts"]
    except yaml.YAMLError as exc:
        print(f"ERROR: {yaml_error(CONFIG, exc)}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: cannot read {CONFIG}: {exc}", file=sys.stderr)
        return 2

    requested = sys.argv[1:]

    if requested:
        unknown = [name for name in requested if name not in accounts]
        if unknown:
            print(
                "ERROR: unknown account(s): " + ", ".join(unknown),
                file=sys.stderr,
            )
            return 2
        selected = requested
        force = True
    else:
        selected = list(accounts)
        force = False

    failures = 0

    for account_id in selected:
        account = accounts[account_id]
        print(f"\n=== {account_id} ({account['address']}) ===")

        for direction, tester, label in (
            ("inbound", test_imap, "IMAP"),
            ("outbound", test_smtp, "SMTP"),
        ):
            cfg = account[direction]

            if not cfg["active"] and not force:
                print(f"{label:<5} SKIP inactive")
                continue

            try:
                tester(cfg)
                print(f"{label:<5} OK   {cfg['host']}:{cfg['port']}")
            except Exception as exc:
                failures += 1
                print(
                    f"{label:<5} FAIL {cfg['host']}:{cfg['port']}  "
                    f"{type(exc).__name__}: {exc}"
                )

    print()
    if failures:
        print(f"FAILED: {failures} connection test(s)")
        return 1

    print("OK: all selected connection tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
