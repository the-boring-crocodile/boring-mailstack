#!/usr/bin/env python3
"""Check the demo's first import against the story, mail by mail.

Runs inside the demo network (see tests/demo/run.sh). For every demo
mailbox it logs in to Stalwart over IMAPS, reads the Message-ID of every
mail in every folder, and compares with what the story says that mailbox
must hold and where (demo/story: deliveries + filing habits):

  missing     a story mail the mailbox should have but does not
  misplaced   present, but in another folder than its owner filed it in
  duplicate   present more than once
  extra       a story mail that does not belong in this mailbox

Special folders are compared by their IMAP role (\\Sent, \\Junk), so the
server's own names ("Sent Items", "Junk Mail") do not matter. Personal
folders must keep their full path and exact name, emoji included.

Also checks provenance: every mail imported outside the Inbox must have
a `provider-mailbox` protection row (PROVENANCE_DB).

Exit 0 only if everything matches. Prints a per-mailbox summary.
"""
import imaplib
import json
import os
import re
import sqlite3
import ssl
import sys
from pathlib import Path

DEMO = Path(os.environ.get("DEMO_SOURCE", "/demo"))
sys.path[:0] = [str(DEMO / "story"), str(DEMO / "seed")]
import story  # noqa: E402
from render import MSGID_DOMAIN, mutf7_decode  # noqa: E402

HOST = os.environ.get("STALWART_HOST", "stalwart.mailstack.local")
LIST_RE = re.compile(rb'^\((?P<flags>[^)]*)\) (?:"(?P<delim>[^"]*)"|NIL) (?P<name>.+)$')
ID_RE = re.compile(r"<([^@>]+)@" + re.escape(MSGID_DOMAIN) + ">")
ROLES = {"\\Sent": "Sent", "\\Junk": "Junk"}


def folders(imap, subscribed_only=False):
    status, data = imap.lsub() if subscribed_only else imap.list()
    out = []
    for line in data or []:
        m = LIST_RE.match(line)
        if not m:
            continue
        name = m["name"].decode()
        if name.startswith('"'):
            name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        flags = m["flags"].decode().split()
        if "\\Noselect" in flags:
            continue
        delim = (m["delim"] or b"/").decode()
        role = next((ROLES[f] for f in flags if f in ROLES), None)
        if name.upper() == "INBOX":
            logical = "INBOX"
        elif role:
            logical = role
        else:
            logical = "/".join(mutf7_decode(name).split(delim))
        out.append((name, logical))
    return out


def story_ids(imap, wire_name):
    status, data = imap.select('"' + wire_name.replace('"', '\\"') + '"', readonly=True)
    if status != "OK" or int(data[0]) == 0:
        return []
    status, data = imap.fetch("1:*", "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    ids = []
    for part in data:
        if isinstance(part, tuple):
            m = ID_RE.search(part[1].decode(errors="replace"))
            ids.append(m[1] if m else None)
    return ids


SIEVE = {}


def main():
    global SIEVE
    accounts = json.loads(Path(os.environ["DEMO_ACCOUNTS"]).read_text())
    if os.environ.get("DEMO_ACCOUNTS_YAML"):   # JSON, written by tools/demo
        configured = json.loads(Path(os.environ["DEMO_ACCOUNTS_YAML"]).read_text())["accounts"]
        SIEVE = {box: (a.get("inbound_sieve") or {}).get("folders", ["INBOX"])
                 for box, a in configured.items()}
    cast, mails = story.load()
    ok = True
    ctx = ssl._create_unverified_context()  # demo Stalwart: self-signed

    prov = {}
    db = os.environ.get("PROVENANCE_DB")
    if db and Path(db).exists():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for account, n in con.execute(
                "select account, count(*) from protected_email "
                "where reason='provider-mailbox' group by account"):
            prov[account] = n

    for box in story.mailboxes(cast):
        want = {}
        for m in mails:
            f = story.deliveries(cast, m).get(box)
            if f is not None:
                want[m.id] = f
        imap = imaplib.IMAP4_SSL(HOST, 993, ssl_context=ctx)
        imap.login(accounts[box]["address"], accounts[box]["password"])
        have = {}
        foreign = 0
        with_mail = set()
        for wire, logical in folders(imap):
            for sid in story_ids(imap, wire):
                with_mail.add((wire, logical))
                if sid is None:
                    foreign += 1
                else:
                    have.setdefault(sid, []).append(logical)
        # Roundcube lists only subscribed folders: every folder the import
        # filled must be subscribed (the bridge creates them so).
        subscribed = {w for w, _ in folders(imap, subscribed_only=True)}
        unsubscribed = sorted(l for w, l in with_mail if l != "INBOX" and w not in subscribed)
        imap.logout()

        missing = sorted(i for i in want if i not in have)
        dup = sorted(i for i, f in have.items() if len(f) > 1)
        extra = sorted(i for i in have if i not in want)
        misplaced = sorted(f"{i}: {have[i][0]!r} instead of {want[i]!r}"
                           for i in want if i in have and len(have[i]) == 1 and have[i][0] != want[i])
        # Mail from provider folders listed in inbound_sieve goes through
        # the filter (SMTP) and is not recorded as placed by a human.
        sieve = {f.casefold() for f in SIEVE.get(box, ["INBOX"])}
        outside_inbox = sum(1 for f in want.values() if f.casefold() not in sieve | {"inbox"})
        prov_n = prov.get(box)
        prov_ok = prov_n is None if not db else prov_n == outside_inbox
        good = not (missing or dup or extra or misplaced or unsubscribed) and prov_ok
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} {box}: {len(want)} expected, "
              f"{sum(len(v) for v in have.values())} found in "
              f"{len({f for v in have.values() for f in v})} folders; "
              f"provenance {prov_n}/{outside_inbox}; non-story mails {foreign}; "
              f"unsubscribed folders {len(unsubscribed)}")
        for label, items in (("missing", missing), ("duplicate", dup),
                             ("extra", extra), ("misplaced", misplaced),
                             ("not subscribed", unsubscribed)):
            for i in items[:12]:
                print(f"     {label}: {i}")
            if len(items) > 12:
                print(f"     {label}: ... {len(items) - 12} more")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
