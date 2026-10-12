#!/usr/bin/env python3
"""Mail Stalwart writes itself goes out under the real address (DECISIONS.md,
"Each account is its real address"): tim's vacation reply to croc travels
tim -> relay -> provider -> getmail -> croc's Inbox. Before, it went out as
tim@mailstack.local and the relay refused it."""
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
                    return 0 if ok else 1
            time.sleep(5)
        print("FAIL vacation reply from the real address: not in croc's Inbox after 240s")
        return 1
    finally:
        restore = [("SETACTIVE \"%s\"" % active.group(1).decode(), None)] if active else [('SETACTIVE ""', None)]
        managesieve("tim", restore + [('DELETESCRIPT "acceptance-vacation"', None)])


if __name__ == "__main__":
    sys.exit(main())
