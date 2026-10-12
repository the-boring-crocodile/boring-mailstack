#!/usr/bin/env python3
"""What a user would notice: every account's mail, flags and Sieve filters.

    state.py snapshot          JSON on stdout: per account, per folder, the
                               sorted (Message-ID, flags) of every message,
                               and the account's Sieve scripts (active marked)
    state.py personalise       give the old stack some user state first:
                               brog gets an active Sieve filter, croc flags
                               the oldest mail in his Inbox
    state.py total             number of messages in all accounts
    state.py export USER DIR   one account's mail as a test fixture:
                               DIR/eml/NNNNNNN.eml (raw), DIR/index.jsonl
                               (folder, flags, internaldate, file per message),
                               DIR/folders.json, DIR/sieve/*.sieve and
                               DIR/sieve.json (active marked); counts on stdout

Runs in a container on the stack's mail network; Stalwart is `stalwart`.
Accounts and passwords: DEMO_ACCOUNTS (the demo's seed-accounts.json).
"""
import base64
import imaplib
import json
import os
import re
import socket
import ssl
import sys
from pathlib import Path

HOST = os.environ.get("STALWART_HOST", "stalwart")
CTX = ssl._create_unverified_context()   # demo Stalwart: self-signed
ACCOUNTS = json.loads(Path(os.environ["DEMO_ACCOUNTS"]).read_text())
LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$')
SIEVE = b'''require ["fileinto"];
# cutover rehearsal: brog's own filter, must survive the cutover
if header :contains "subject" "PondPulse" { fileinto "INBOX"; }
'''


def imap(user):
    c = imaplib.IMAP4_SSL(HOST, 993, ssl_context=CTX)
    c.login(user, ACCOUNTS[user]["password"])
    return c


def folders(c):
    typ, data = c.list()
    out = []
    for line in data:
        m = LIST_RE.match(line)
        if m and b"\\Noselect" not in m["flags"]:
            out.append(m["name"].decode())
    return sorted(out)


def messages(c, folder):
    typ, _ = c.select(folder, readonly=True)
    if typ != "OK":
        return None
    typ, data = c.fetch("1:*", "(FLAGS BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    rows = []
    for item in data:
        if not isinstance(item, tuple):
            continue
        flags = re.search(rb"FLAGS \(([^)]*)\)", item[0])
        flags = sorted(f for f in (flags[1].decode().split() if flags else []) if f != "\\Recent")
        mid = item[1].decode(errors="replace").split(":", 1)[-1].strip()
        rows.append([mid, flags])
    return sorted(rows)


class Sieve:
    """Just enough ManageSieve (RFC 5804): STARTTLS, PLAIN, a few commands."""

    def __init__(self, user):
        self.s = socket.create_connection((HOST, 4190), timeout=20)
        self.f = self.s.makefile("rb")
        self.response()
        self.command(b"STARTTLS")
        self.s = CTX.wrap_socket(self.s, server_hostname=HOST)
        self.f = self.s.makefile("rb")
        self.response()                      # capabilities again, after TLS
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
                raise RuntimeError(f"ManageSieve: {line.decode().strip()}")
            lines.append(line.rstrip(b"\r\n"))

    def command(self, cmd):
        self.s.sendall(cmd + b"\r\n")
        return self.response()

    def scripts(self):
        out = {}
        for line in self.command(b"LISTSCRIPTS"):
            m = re.match(rb'"([^"]*)"( ACTIVE)?', line)
            if m:
                out[m[1].decode()] = bool(m[2])
        return out

    def get(self, name):
        self.s.sendall(b'GETSCRIPT "' + name.encode() + b'"\r\n')
        head = self.f.readline()
        m = re.match(rb"\{(\d+)\+?\}", head)
        if not m:
            raise RuntimeError(f"ManageSieve GETSCRIPT: {head[:80]!r}")
        body = self.f.read(int(m[1]))
        self.response()
        return body

    def put(self, name, body):
        self.command(b'PUTSCRIPT "' + name.encode() + b'" {' + str(len(body)).encode() + b"+}\r\n" + body)
        self.command(b'SETACTIVE "' + name.encode() + b'"')


def snapshot():
    state = {}
    for user in sorted(ACCOUNTS):
        try:
            c = imap(user)
        except imaplib.IMAP4.error:
            state[user] = {"login": "failed", "mail": {}, "sieve": {}}
            continue
        try:
            mail = {f: messages(c, f) for f in folders(c)}
        finally:
            c.logout()
        state[user] = {"mail": mail, "sieve": Sieve(user).scripts()}
    return state


def personalise():
    Sieve("brog").put("rehearsal", SIEVE)
    c = imap("croc")
    try:
        c.select("INBOX")
        c.store("1", "+FLAGS", "(\\Flagged)")
    finally:
        c.logout()


FETCH_RE = re.compile(rb"UID (\d+)|FLAGS \(([^)]*)\)|INTERNALDATE \"([^\"]+)\"")


def export(user, out):
    out = Path(out)
    (out / "eml").mkdir(parents=True, exist_ok=True)
    c = imap(user)
    n = 0
    names = folders(c)
    with open(out / "index.jsonl", "w") as index:
        for folder in names:
            if c.select(folder, readonly=True)[0] != "OK":
                continue
            typ, data = c.uid("SEARCH", None, "ALL")
            uids = data[0].split() if data and data[0] else []
            for i in range(0, len(uids), 200):
                chunk = b",".join(uids[i:i + 200]).decode()
                typ, data = c.uid("FETCH", chunk, "(UID FLAGS INTERNALDATE BODY.PEEK[])")
                for item in data:
                    if not isinstance(item, tuple):
                        continue
                    meta = {"uid": None, "flags": [], "internaldate": None}
                    for m in FETCH_RE.finditer(item[0]):
                        if m[1]:
                            meta["uid"] = int(m[1])
                        elif m[2] is not None:
                            meta["flags"] = [f for f in m[2].decode().split() if f != "\\Recent"]
                        elif m[3]:
                            meta["internaldate"] = m[3].decode()
                    n += 1
                    name = f"{n:07d}.eml"
                    (out / "eml" / name).write_bytes(item[1])
                    index.write(json.dumps({"folder": folder, "file": name, **meta}) + "\n")
    c.logout()
    (out / "folders.json").write_text(json.dumps(names, indent=1) + "\n")
    s = Sieve(user)
    scripts = s.scripts()
    (out / "sieve").mkdir(exist_ok=True)
    for name in scripts:
        (out / "sieve" / f"{name}.sieve").write_bytes(s.get(name))
    (out / "sieve.json").write_text(json.dumps(scripts, indent=1) + "\n")
    return {"folders": len(names), "messages": n, "sieve_scripts": len(scripts),
            "active_sieve": sum(scripts.values())}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "snapshot":
        print(json.dumps(snapshot(), sort_keys=True))
    elif cmd == "personalise":
        personalise()
        print("personalised: brog has an active Sieve filter, croc a flagged mail")
    elif cmd == "export" and len(sys.argv) == 4:
        print(json.dumps(export(sys.argv[2], sys.argv[3])))
    elif cmd == "total":
        print(sum(len(m or []) for a in snapshot().values() for m in a["mail"].values()))
    else:
        sys.exit(__doc__)
