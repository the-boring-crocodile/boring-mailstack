#!/usr/bin/env python3
"""Inbound paths on a running demo (see tests/demo/run.sh), account brog,
whose provider Junk goes through the filter (tools/demo: inbound_sieve).

1. Provider Junk through the filter: a mail matching brog's rule lands in
   the rule's folder; one that does not lands in Junk, flagged $Junk.
2. Provider move: a mail fetched into the Inbox is moved at the provider
   into a new folder; here the same mail (same Email id) moves too, is
   recorded as placed by a human, and exists once.
3. Provider label: the same mail copied at the provider into one more new
   folder; here it is one mail in both folders.
4. Filter change, Junk resievable (tools/demo: brog's never_move_from has
   no Junk): spam a new rule matches leaves Junk and loses its junk flag;
   spam no rule matches stays in Junk.
5. Re-sort chute: mails a human moves into INBOX go back to the filter:
   a rule matches -> its folder; no rule -> stays in INBOX. Both are no
   longer marked as placed by a human.
"""
import base64
import imaplib
import json
import os
import re
import socket
import sqlite3
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path

HOST = "stalwart.mailstack.local"
PROVIDER = ("mail.provider.test", 3993)
BOX = "brog"
CTX = ssl._create_unverified_context()      # demo Stalwart: self-signed
PCTX = ssl.create_default_context(cafile=os.environ["DEMO_CA_FILE"])
ACCOUNTS = json.loads(Path(os.environ["DEMO_ACCOUNTS"]).read_text())
TAG = str(int(time.time()))
results = []


def check(name, ok, detail):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def quoted(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def here():
    c = imaplib.IMAP4_SSL(HOST, 993, ssl_context=CTX)
    c.login(ACCOUNTS[BOX]["address"], ACCOUNTS[BOX]["password"])
    return c


def provider():
    c = imaplib.IMAP4_SSL(*PROVIDER, ssl_context=PCTX)
    c.login(ACCOUNTS[BOX]["address"], ACCOUNTS[BOX]["password"])
    return c


def mail(subject):
    m = EmailMessage()
    m["From"] = "someone@outside.test"
    m["To"] = ACCOUNTS[BOX]["address"]
    m["Subject"] = f"{subject}-{TAG}"
    m["Message-ID"] = f"<{subject}.{TAG}@inbound.test>"
    m["Date"] = "Fri, 09 Oct 2026 15:00:00 +0200"
    m.set_content(f"inbound test {subject}")
    return m.as_bytes()


def where(subject):
    """{folder: [(EMAILID, flags)]} for mails whose Subject has subject-TAG."""
    c = here()
    out = {}
    typ, lst = c.list()
    for line in lst:
        m = re.search(rb'"([^"]+)"$', line) or re.search(rb' (\S+)$', line)
        name = m.group(1).decode()
        if c.select(quoted(name), readonly=True)[0] != "OK":
            continue
        typ, data = c.fetch("1:*", "(OBJECTID FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
        for item in data or []:
            if isinstance(item, tuple) and f"{subject}-{TAG}".encode() in item[1]:
                eid = re.search(rb"EMAILID \(?([^ )]+)", item[0]).group(1).decode()
                flags = re.search(rb"FLAGS \(([^)]*)\)", item[0]).group(1).decode()
                out.setdefault(name, []).append((eid, flags))
    c.logout()
    return out


def wait_for(subject, done, timeout=240):
    seen = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        seen = where(subject)
        if done(seen):
            return seen
        time.sleep(5)
    return seen


def protected(email_id):
    con = sqlite3.connect(f"file:{os.environ['PROVENANCE_DB']}?mode=ro", uri=True)
    return con.execute("select reason from protected_email where account=? and email_id=?",
                       (BOX, email_id)).fetchone()


SCRIPT = (b'require ["fileinto", "mailbox"];\r\n'
          b'if header :contains "subject" "INB-junkrule" { fileinto :create "Filtered from Junk"; }\r\n')


def managesieve(script):
    s = socket.create_connection((HOST, 4190), 20)
    f = s.makefile("rb")

    def resp():
        while True:
            line = f.readline()
            if not line or re.match(rb"^(OK|NO|BYE)", line):
                return line

    resp()
    s.sendall(b"STARTTLS\r\n"); resp()
    s = CTX.wrap_socket(s, server_hostname=HOST); f = s.makefile("rb"); resp()
    token = base64.b64encode(f"\0{ACCOUNTS[BOX]['address']}\0{ACCOUNTS[BOX]['password']}".encode()).decode()
    s.sendall(f'AUTHENTICATE "PLAIN" "{token}"\r\n'.encode())
    assert resp().startswith(b"OK"), "managesieve login"
    s.sendall(f'PUTSCRIPT "inbound-test" {{{len(script)}+}}\r\n'.encode() + script + b"\r\n")
    assert resp().startswith(b"OK"), "putscript"
    s.sendall(b'SETACTIVE "inbound-test"\r\n')
    assert resp().startswith(b"OK"), "setactive"
    s.close()


def junk_folder(c):
    typ, lst = c.list()
    for line in lst:
        if b"\\Junk" in line:
            return re.search(rb'"([^"]+)"$', line).group(1).decode()
    return "Junk"


def main():
    # 1. Provider Junk through the filter.
    managesieve(SCRIPT)
    p = provider()
    typ, lst = p.list()
    if not any(b'"Junk"' in l or l.endswith(b" Junk") for l in lst):
        p.create("Junk")
    for subject in ("INB-junkrule", "INB-junkplain"):
        p.append("Junk", None, None, mail(subject))
    # getmail waits on the provider INBOX (IDLE) and fetches every folder
    # when it wakes: new INBOX mail wakes it.
    p.append("INBOX", None, None, mail("INB-wake"))
    p.logout()
    c = here(); junk = junk_folder(c); c.logout()
    rule = wait_for("INB-junkrule", lambda s: bool(s))
    plain = wait_for("INB-junkplain", lambda s: bool(s))
    check("provider Junk, filter rule matches", list(rule) == ["Filtered from Junk"], f"found in {sorted(rule)}")
    check("provider Junk, no rule: Junk, flagged", list(plain) == [junk] and "$Junk" in plain[junk][0][1],
          f"found in {plain}")

    # 2. Provider move.
    p = provider()
    p.append("INBOX", None, None, mail("INB-move"))
    p.logout()
    first = wait_for("INB-move", lambda s: "INBOX" in s)
    eid = first.get("INBOX", [("?", "")])[0][0]
    p = provider()
    p.create(f"Kept {TAG}")
    p.select("INBOX")
    typ, data = p.search(None, "SUBJECT", f'"INB-move-{TAG}"')
    num = data[0].split()[-1]
    p.copy(num, quoted(f"Kept {TAG}"))
    p.store(num, "+FLAGS", "\\Deleted")
    p.expunge()
    p.logout()
    moved = wait_for("INB-move", lambda s: list(s) == [f"Kept {TAG}"])
    check("provider move becomes a move here",
          list(moved) == [f"Kept {TAG}"] and [e for e, _ in moved[f"Kept {TAG}"]] == [eid] and bool(protected(eid)),
          f"before {first}, after {moved}, provenance {protected(eid)}")

    # 3. Provider label (copy into another folder).
    p = provider()
    p.create(f"Label {TAG}")
    p.select(quoted(f"Kept {TAG}"))
    typ, data = p.search(None, "SUBJECT", f'"INB-move-{TAG}"')
    p.copy(data[0].split()[-1], quoted(f"Label {TAG}"))
    p.logout()
    both = wait_for("INB-move", lambda s: len(s) == 2)
    check("provider label adds a folder to the same mail",
          sorted(both) == sorted([f"Kept {TAG}", f"Label {TAG}"])
          and {e for v in both.values() for e, _ in v} == {eid},
          f"found {both}")
    # 4. Filter change pulls matching spam out of Junk.
    p = provider()
    p.append("Junk", None, None, mail("INB-junklater"))
    p.append("INBOX", None, None, mail("INB-wake2"))
    p.logout()
    wait_for("INB-junklater", lambda s: junk in s)
    managesieve(SCRIPT + b'if header :contains "subject" "INB-junklater" { fileinto :create "Later from Junk"; }\r\n')
    later = wait_for("INB-junklater", lambda s: "Later from Junk" in s, timeout=300)
    plain = where("INB-junkplain")
    check("filter change: a rule takes spam out of Junk, junk flag gone",
          list(later) == ["Later from Junk"] and "$Junk" not in later["Later from Junk"][0][1], f"found {later}")
    check("filter change: spam without a rule stays in Junk",
          list(plain) == [junk] and "$Junk" in plain[junk][0][1], f"found {plain}")

    # 5. Re-sort chute.
    managesieve(SCRIPT + b'if header :contains "subject" "INB-junklater" { fileinto :create "Later from Junk"; }\r\n'
                + b'if header :contains "subject" "INB-move" { fileinto :create "Resorted"; }\r\n')
    p = provider()
    p.create(f"Hand {TAG}")
    p.append(quoted(f"Hand {TAG}"), None, None, mail("INB-stay"))
    p.logout()
    stay = wait_for("INB-stay", lambda s: f"Hand {TAG}" in s)
    stay_id = stay.get(f"Hand {TAG}", [("?", "")])[0][0]
    time.sleep(90)       # the filter change's own run is over
    c = here()
    for folder, subject in ((f"Kept {TAG}", "INB-move"), (f"Hand {TAG}", "INB-stay")):
        c.select(quoted(folder))
        typ, data = c.uid("SEARCH", None, "ALL")
        for uid in data[0].split():
            typ, head = c.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
            if f"{subject}-{TAG}".encode() in head[0][1]:
                c.uid("MOVE", uid, "INBOX")
    c.logout()
    # The mail is also in "Label" (a human's placement): that folder stays.
    resorted = wait_for("INB-move", lambda s: sorted(s) == sorted(["Resorted", f"Label {TAG}"]), timeout=300)
    stayed = where("INB-stay")
    check("re-sort chute: a rule matches -> its folder, released",
          sorted(resorted) == sorted(["Resorted", f"Label {TAG}"]) and not protected(eid),
          f"found {resorted}, provenance {protected(eid)}")
    check("re-sort chute: no rule -> stays in INBOX, released",
          list(stayed) == ["INBOX"] and not protected(stay_id), f"found {stayed}, provenance {protected(stay_id)}")

    # 6. "Not spam" sticks: spam moved by hand from Junk to INBOX stays there
    # after the next filter change (the move is recorded as $notjunk).
    c = here()
    junk = junk_folder(c)
    c.select(quoted(junk))
    typ, data = c.uid("SEARCH", None, "ALL")
    for uid in data[0].split():
        typ, head = c.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
        if f"INB-junkplain-{TAG}".encode() in head[0][1]:
            c.uid("MOVE", uid, "INBOX")
    c.logout()
    marked = wait_for("INB-junkplain", lambda s: list(s) == ["INBOX"] and "$notjunk" in s["INBOX"][0][1].lower(),
                      timeout=300)
    managesieve(SCRIPT + b'if header :contains "subject" "INB-nothing" { fileinto :create "Nothing"; }\r\n')
    time.sleep(90)       # the filter change's run
    after = where("INB-junkplain")
    check("not spam: Junk -> INBOX by hand, marked not junk", list(marked) == ["INBOX"]
          and "$notjunk" in marked["INBOX"][0][1].lower(), f"found {marked}")
    check("not spam: still in INBOX after a filter change", list(after) == ["INBOX"], f"found {after}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
