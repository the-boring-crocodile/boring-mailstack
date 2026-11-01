#!/usr/bin/env python3
"""Mail Stalwart writes itself goes out under the real address (DECISIONS.md,
"Each account is its real address"): tim's vacation reply to croc travels
tim -> relay -> provider -> getmail -> croc's Inbox. Before, it went out as
tim@mailstack.local and the relay refused it.

And it is not sent where it would stir things up (docs/USING.md, "Good to
know"): brog writes to a group address with tim only in the envelope, otter
writes to tim with a List-Id header. Each would get a first reply otherwise
(one per sender and interval), yet neither may get one."""
import base64
import imaplib
import json
import os
import re
import smtplib
import socket
import ssl
import sys
import time
import uuid
from email.message import EmailMessage
from pathlib import Path

HOST = "stalwart.mailstack.local"
CTX = ssl._create_unverified_context()
ACCOUNTS = json.loads(Path(os.environ["DEMO_ACCOUNTS"]).read_text())


def managesieve(user, commands):
    s = socket.create_connection((HOST, 4190), 20)
    f = s.makefile("rb")

    def resp():
        out = b""
        while True:
            line = f.readline()
            out += line
            m = re.search(rb"\{(\d+)\}\r\n$", line)
            if m:
                out += f.read(int(m.group(1)))
            if not line or re.match(rb"^(OK|NO|BYE)", line):
                return out

    resp()
    s.sendall(b"STARTTLS\r\n"); resp()
    s = CTX.wrap_socket(s, server_hostname=HOST); f = s.makefile("rb"); resp()
    token = base64.b64encode(f"\0{ACCOUNTS[user]['address']}\0{ACCOUNTS[user]['password']}".encode()).decode()
    s.sendall(f'AUTHENTICATE "PLAIN" "{token}"\r\n'.encode())
    assert resp().startswith(b"OK"), "managesieve login"
    out = []
    for command, literal in commands:
        s.sendall(command.encode() + (f" {{{len(literal)}+}}\r\n".encode() + literal if literal else b"") + b"\r\n")
        out.append(resp())
    s.close()
    return out


def send(sender, to_header, rcpt, subject, extra=None):
    msg = EmailMessage()
    msg["From"] = ACCOUNTS[sender]["address"]
    msg["To"] = to_header
    msg["Subject"] = subject
    for name, value in (extra or {}).items():
        msg[name] = value
    msg.set_content("For the whole team.\n")
    with smtplib.SMTP_SSL(HOST, 465, context=CTX, timeout=30) as s:
        s.login(ACCOUNTS[sender]["address"], ACCOUNTS[sender]["password"])
        s.send_message(msg, to_addrs=[rcpt])


def count(user, subject):
    """Mails whose subject contains `subject`, in every folder of `user`."""
    c = imaplib.IMAP4_SSL(HOST, 993, ssl_context=CTX)
    c.login(ACCOUNTS[user]["address"], ACCOUNTS[user]["password"])
    n = 0
    for line in c.list()[1] or []:
        m = re.match(rb'^\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$', line)
        if not m or b"\\Noselect" in m["flags"]:
            continue
        name = m["name"].decode()
        if c.select(name if name.startswith('"') else f'"{name}"', readonly=True)[0] != "OK":
            continue
        typ, data = c.search(None, "SUBJECT", f'"{subject}"')
        n += len(data[0].split()) if data and data[0] else 0
    c.logout()
    return n


def main():
    marker = f"Vacation {uuid.uuid4().hex[:8]}"
    listing = managesieve("tim", [("LISTSCRIPTS", None)])[0]
    active = re.search(rb'"([^"]+)" ACTIVE', listing)
    script = (b'require ["vacation"];\r\n'
              b'vacation :days 1 :subject "Away: ' + marker.encode() + b'" "Tim is out (acceptance test).";\r\n')
    managesieve("tim", [('PUTSCRIPT "acceptance-vacation"', script), ('SETACTIVE "acceptance-vacation"', None)])
    try:
        msg = EmailMessage()
        msg["From"] = "Croc <croc@pond.test>"
        msg["To"] = "Tim <tim@pond.test>"
        msg["Subject"] = f"Question — {marker}"
        msg.set_content("Tim, are you there?\n\nCroc\n")
        t0 = time.time()
        with smtplib.SMTP_SSL(HOST, 465, context=CTX, timeout=30) as s:
            s.login(ACCOUNTS["croc"]["address"], ACCOUNTS["croc"]["password"])
            s.send_message(msg)
        c = imaplib.IMAP4_SSL(HOST, 993, ssl_context=CTX)
        c.login(ACCOUNTS["croc"]["address"], ACCOUNTS["croc"]["password"])
        while time.time() - t0 < 240:
            c.select("INBOX", readonly=True)
            typ, data = c.fetch("1:*", "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM RETURN-PATH)])")
            for item in data or []:
                if isinstance(item, tuple) and f"Away: {marker}".encode() in item[1]:
                    head = item[1].decode(errors="replace")
                    ok = "tim@pond.test" in head and "mailstack.local" not in head
                    print(f"{'PASS' if ok else 'FAIL'} vacation reply from the real address: "
                          f"in croc's Inbox after {time.time() - t0:.0f}s; {' '.join(head.split())}")
                    return (0 if ok else 1) | no_stir(marker, time.time() - t0)
            time.sleep(5)
        print("FAIL vacation reply from the real address: not in croc's Inbox after 240s")
        return 1
    finally:
        restore = [("SETACTIVE \"%s\"" % active.group(1).decode(), None)] if active else [('SETACTIVE ""', None)]
        managesieve("tim", restore + [('DELETESCRIPT "acceptance-vacation"', None)])


def no_stir(marker, took):
    """The two mails that must not be answered. Waits until both are in tim's
    mailbox (getmail may take them in its next round), then four times as
    long as the answered one took (at least 60 s) before looking for replies."""
    tim = ACCOUNTS["tim"]["address"]
    cases = (("brog", "Team news", "mail to a group address (tim only in the envelope)"),
             ("otter", "List digest", "mail with a List-Id header"))
    send("brog", "All of Pond Ltd <all@lists.pond.test>", tim, f"Team news - {marker}")
    send("otter", f"Tim <{tim}>", tim, f"List digest - {marker}",
         {"List-Id": "Pond Ltd team <team.lists.pond.test>"})
    t0 = time.time()
    while time.time() - t0 < 240 and not all(count("tim", f"{s} - {marker}") for _, s, _ in cases):
        time.sleep(5)
    time.sleep(max(60, 4 * took))
    status = 0
    for user, subject, what in cases:
        arrived = count("tim", f"{subject} - {marker}")
        n = count(user, f"Away: {marker}")
        ok = arrived == 1 and n == 0
        print(f"{'PASS' if ok else 'FAIL'} no vacation reply to {what}: reached tim {arrived}x, "
              f"{n} replies in {user}'s mailbox")
        status |= not ok
    return status


if __name__ == "__main__":
    sys.exit(main())
