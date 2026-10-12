#!/usr/bin/env python3
"""Load an account export (tests/resieve/state.py export) into a demo account.

    fixture.py load ACCOUNT EXPORT_DIR [--empty-first]
    fixture.py count ACCOUNT

Runs in a container on the demo's mail network (Stalwart is
stalwart.mailstack.local). load: creates the export's folders, appends every
message with its flags and arrival date, uploads the Sieve scripts and
activates the one that was active. --empty-first deletes the account's
existing mail first (the demo story), so the account holds only the export.
Counts only on stdout, never content.
Accounts: DEMO_ACCOUNTS (the demo's seed-accounts.json).
"""
import base64
import imaplib
import json
import os
import re
import socket
import ssl
import sys
import time
from pathlib import Path

HOST = os.environ.get("STALWART_HOST", "stalwart.mailstack.local")
CTX = ssl._create_unverified_context()          # demo Stalwart: self-signed
ACCOUNTS = json.loads(Path(os.environ.get("DEMO_ACCOUNTS", "/a.json")).read_text())
LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$')


def imap(user):
    c = imaplib.IMAP4_SSL(HOST, 993, ssl_context=CTX)
    c.login(user, ACCOUNTS[user]["password"])
    return c


def quoted(name):
    """Folder names as the export has them (LIST form, maybe quoted)."""
    if name.startswith('"'):
        return name
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def bare(name):
    return name[1:-1] if name.startswith('"') else name


def folders(c):
    out = []
    for line in c.list()[1]:
        m = LIST_RE.match(line)
        if m and b"\\Noselect" not in m["flags"]:
            out.append(m["name"].decode())
    return out


def empty(c):
    n = 0
    for f in folders(c):
        if c.select(quoted(f))[0] != "OK":
            continue
        typ, data = c.search(None, "ALL")
        ids = data[0].split() if data and data[0] else []
        if ids:
            c.store(b",".join(ids).decode(), "+FLAGS.SILENT", "(\\Deleted)")
            c.expunge()
            n += len(ids)
    return n


class Sieve:
    """Just enough ManageSieve (RFC 5804): STARTTLS, PLAIN, PUTSCRIPT, SETACTIVE."""

    def __init__(self, user):
        self.s = socket.create_connection((HOST, 4190), timeout=30)
        self.f = self.s.makefile("rb")
        self.response()
        self.command(b"STARTTLS")
        self.s = CTX.wrap_socket(self.s, server_hostname=HOST)
        self.f = self.s.makefile("rb")
        self.response()
        token = base64.b64encode(b"\0" + user.encode() + b"\0" + ACCOUNTS[user]["password"].encode())
        self.command(b'AUTHENTICATE "PLAIN" "' + token + b'"')

    def response(self):
        lines = []
        while True:
            line = self.f.readline()
            if not line:
                raise RuntimeError("ManageSieve: connection closed")
            if line.startswith(b"OK"):
                return lines
            if line.startswith((b"NO", b"BYE")):
                raise RuntimeError(f"ManageSieve: {line.decode(errors='replace').strip()}")
            lines.append(line)

    def command(self, cmd):
        self.s.sendall(cmd + b"\r\n")
        return self.response()

    def put(self, name, body, active):
        self.command(b'PUTSCRIPT "' + name.encode() + b'" {' + str(len(body)).encode() + b"+}\r\n" + body)
        if active:
            self.command(b'SETACTIVE "' + name.encode() + b'"')


def load(user, export, empty_first):
    export = Path(export)
    c = imap(user)
    removed = empty(c) if empty_first else 0
    have = {bare(f) for f in folders(c)}
    wanted = json.loads((export / "folders.json").read_text())
    created = 0
    for f in sorted(wanted, key=lambda n: bare(n).count("/")):
        if bare(f) not in have and bare(f).upper() != "INBOX":
            if c.create(quoted(f))[0] == "OK":
                created += 1
            c.subscribe(quoted(f))
    n = failed = 0
    started = time.time()
    with open(export / "index.jsonl") as index:
        for line in index:
            row = json.loads(line)
            raw = (export / "eml" / row["file"]).read_bytes()
            flags = f'({" ".join(row["flags"])})' if row["flags"] else None
            date = f'"{row["internaldate"]}"' if row.get("internaldate") else None
            try:
                typ, _ = c.append(quoted(row["folder"]), flags, date, raw)
            except imaplib.IMAP4.error:
                typ = "NO"
            if typ == "OK":
                n += 1
            else:
                failed += 1
            if (n + failed) % 2000 == 0:
                print(f"  {n + failed} ...", file=sys.stderr, flush=True)
    c.logout()
    scripts = json.loads((export / "sieve.json").read_text())
    if scripts:
        s = Sieve(user)
        for name, active in scripts.items():
            s.put(name, (export / "sieve" / f"{name}.sieve").read_bytes(), active)
    return {"removed_first": removed, "folders_created": created, "appended": n, "failed": failed,
            "sieve_scripts": len(scripts), "seconds": round(time.time() - started)}


def count(user):
    c = imap(user)
    total = 0
    names = folders(c)
    for f in names:
        typ, data = c.status(quoted(f), "(MESSAGES)")
        m = re.search(rb"MESSAGES (\d+)", data[0] or b"")
        total += int(m[1]) if m else 0
    c.logout()
    return {"folders": len(names), "messages": total}


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "load":
        print(json.dumps(load(a[1], a[2], "--empty-first" in a[3:])))
    elif len(a) == 2 and a[0] == "count":
        print(json.dumps(count(a[1])))
    else:
        sys.exit(__doc__)
