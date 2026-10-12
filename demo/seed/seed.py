#!/usr/bin/env python3
"""Seed the demo provider with the Operation Lighthouse season.

Runs once, inside the demo (service demo-seed), before the stack's first
import. For each demo mailbox it logs in at the provider over IMAPS
(verifying the demo CA), creates the character's folders and appends
every mail the story gives that mailbox, in the folder its owner would
have filed it in, with the story's date as the arrival date.

Environment: DEMO_PROVIDER_HOST, DEMO_PROVIDER_IMAP_PORT, DEMO_CA_FILE,
DEMO_ACCOUNTS (JSON: {mailbox: {address, password}}), DEMO_TZ.
"""
import imaplib
import json
import os
import socket
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORY = HERE.parent / "story"
sys.path.insert(0, str(STORY))
sys.path.insert(0, str(HERE))

import story  # noqa: E402
from render import anchor_times, mutf7_encode, render  # noqa: E402

UNREAD_DAYS = 10   # the finale arrives unread; everything older is read


def zone(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # the name is checked by tools/demo: no tz database here
        print(f"seed: no time zone database in this image for {name!r}; story times in UTC", flush=True)
        return timezone.utc


def connect(host, port, ca_file):
    context = ssl.create_default_context(cafile=ca_file)
    for attempt in range(60):
        try:
            return imaplib.IMAP4_SSL(host, port, ssl_context=context, timeout=20)
        except (ConnectionError, TimeoutError, socket.gaierror, OSError):
            if attempt == 59:
                raise
            time.sleep(1)


def quoted(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def delimiter(imap):
    status, data = imap.list('""', '""')
    if status != "OK" or not data or data[0] is None:
        return "."
    # (\Noselect) "." ""
    raw = data[0].decode()
    first = raw.index('"')
    return raw[first + 1:raw.index('"', first + 1)] or "."


def count(imap, wire_name):
    status, data = imap.select(quoted(wire_name), readonly=True)
    if status != "OK":
        raise RuntimeError(f"cannot select {wire_name}")
    return int(data[0])


def ensure_folder(imap, folder, delim, created):
    parts = folder.split("/")
    for i in range(1, len(parts) + 1):
        wire = mutf7_encode(delim.join(parts[:i]))
        if wire in created or wire.upper() == "INBOX":
            continue
        status, data = imap.list('""', quoted(wire))
        if status == "OK" and data and data[0] is not None:
            created.add(wire)
            continue
        status, data = imap.create(quoted(wire))
        if status != "OK":
            raise RuntimeError(f"cannot create folder {folder!r}: {data}")
        created.add(wire)
    return mutf7_encode(delim.join(parts))


def seed_mailbox(imap, box, cast, mails, by_id, at, now):
    plan = []
    for m in mails:
        folder = story.deliveries(cast, m).get(box)
        if folder is not None:
            plan.append((m, folder))

    delim = delimiter(imap)
    created = set()
    wires = {f: ensure_folder(imap, f, delim, created) for f in {f for _, f in plan}}
    expected = {}
    for _, f in plan:
        expected[wires[f]] = expected.get(wires[f], 0) + 1

    present = {w: count(imap, w) for w in expected}
    # More than planned is fine: mail sent within the demo arrives here too.
    if all(present[w] >= n for w, n in expected.items()):
        print(f"seed: {box}: already seeded ({len(plan)} mails)", flush=True)
        return
    if any(present.values()):
        raise RuntimeError(f"{box}: provider mailbox is neither empty nor fully seeded: {present}")

    for m, folder in plan:
        when = at(m.day, m.hour, m.minute)
        flags = "" if (folder != "Sent" and now - when < timedelta(days=UNREAD_DAYS)) else "(\\Seen)"
        raw = render(cast, m, by_id, at, STORY / "attachments")
        status, data = imap.append(quoted(wires[folder]), flags, imaplib.Time2Internaldate(when), raw)
        if status != "OK":
            raise RuntimeError(f"{box}: append {m.id} to {folder!r} failed: {data}")

    after = {w: count(imap, w) for w in expected}
    if after != expected:
        raise RuntimeError(f"{box}: seeded counts {after} differ from plan {expected}")
    detail = ", ".join(f"{f} {expected[wires[f]]}" for f in sorted(wires))
    print(f"seed: {box}: {len(plan)} mails ({detail})", flush=True)


def main():
    host = os.environ["DEMO_PROVIDER_HOST"]
    port = int(os.environ.get("DEMO_PROVIDER_IMAP_PORT", "3993"))
    ca_file = os.environ["DEMO_CA_FILE"]
    accounts = json.loads(Path(os.environ["DEMO_ACCOUNTS"]).read_text())
    tz = zone(os.environ.get("DEMO_TZ", "Europe/London"))

    cast, mails = story.load()
    errors = story.check(cast, mails)
    if errors:
        for e in errors:
            print("seed: story error:", e, flush=True)
        return 1
    by_id = {m.id: m for m in mails}
    now = datetime.now(timezone.utc)
    at = anchor_times(now, tz)

    for box in story.mailboxes(cast):
        acct = accounts[box]
        imap = connect(host, port, ca_file)
        try:
            imap.login(acct["address"], acct["password"])
            seed_mailbox(imap, box, cast, mails, by_id, at, now)
        finally:
            try:
                imap.logout()
            except (OSError, imaplib.IMAP4.error):
                pass
    print("seed: done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
