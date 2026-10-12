#!/usr/bin/env python3
"""A provider with labels (Gmail), on a running demo (tests/demo/run.sh),
account tim. GreenMail has no all-mail view, so this script plays getmail:
it hands mails to the bridge the way getmail/handoff.py does, with
LABELS:yes and the provider's folder roles, and checks the result in
Stalwart.

1. New mail in INBOX: through the filter into INBOX.
2. The same mail under a label: one mail in INBOX and the label's folder.
3. Marked as spam at the provider: it leaves INBOX and the label, only in
   Junk, flagged junk (found live 2026-10-09: it stayed in INBOX too).
4. "Not spam" at the provider: back in INBOX only, flagged not junk.
5. Deleted at the provider: only in Trash. 6. Restored: only in INBOX.
"""
import socket
import sys
import time

import inbound
from inbound import check, mail, wait_for

inbound.BOX = "tim"
BRIDGE = ("mail-bridge", 8025)


def handoff(mailbox, raw, role=""):
    head = f"ACCOUNT:{inbound.BOX}\nMAILBOX:{mailbox}\nSENDER:someone@outside.test\n"
    if role:
        head += f"ROLE:{role}\n"
    head += "DELIMITER:/\nLABELS:yes\n\n"
    with socket.create_connection(BRIDGE, timeout=30) as s:
        s.settimeout(300)
        s.sendall(head.encode() + raw)
        s.shutdown(socket.SHUT_WR)
        response = b""
        while chunk := s.recv(4096):
            response += chunk
    return response.strip()


def junk_and_trash():
    c = inbound.here()
    names = {}
    typ, lst = c.list()
    for line in lst:
        for flag, role in ((b"\\Junk", "junk"), (b"\\Trash", "trash")):
            if flag in line:
                names[role] = inbound.re.search(rb'"([^"]+)"$', line).group(1).decode()
    c.logout()
    return names.get("junk", "Junk"), names.get("trash", "Trash")


def main():
    raw = mail("LBL-gmail")
    subject = "LBL-gmail"
    junk, trash = junk_and_trash()
    label = f"Label {inbound.TAG}"

    ok = handoff("INBOX", raw) == b"OK"
    first = wait_for(subject, lambda s: "INBOX" in s, timeout=120)
    check("labels: new mail into INBOX", ok and list(first) == ["INBOX"], f"found {first}")
    eid = first.get("INBOX", [("?", "")])[0][0]

    ok = handoff(label, raw) == b"OK"
    both = wait_for(subject, lambda s: len(s) == 2, timeout=60)
    check("labels: a label adds a folder, INBOX stays",
          ok and sorted(both) == sorted(["INBOX", label])
          and {e for v in both.values() for e, _ in v} == {eid}, f"found {both}")

    ok = handoff("[Gmail]/Spam", raw, role="junk") == b"OK"
    spam = wait_for(subject, lambda s: list(s) == [junk], timeout=60)
    check("labels: marked as spam -> only in Junk, flagged junk",
          ok and list(spam) == [junk] and "$junk" in spam[junk][0][1].lower()
          and spam[junk][0][0] == eid, f"found {spam}")

    ok = handoff("INBOX", raw) == b"OK"
    back = wait_for(subject, lambda s: list(s) == ["INBOX"], timeout=60)
    check("labels: not spam -> only in INBOX, flagged not junk",
          ok and list(back) == ["INBOX"] and "$notjunk" in back["INBOX"][0][1].lower(), f"found {back}")

    ok = handoff("[Gmail]/Trash", raw, role="trash") == b"OK"
    gone = wait_for(subject, lambda s: list(s) == [trash], timeout=60)
    check("labels: deleted -> only in Trash", ok and list(gone) == [trash], f"found {gone}")

    ok = handoff("INBOX", raw) == b"OK"
    restored = wait_for(subject, lambda s: list(s) == ["INBOX"], timeout=60)
    check("labels: restored from the trash -> only in INBOX",
          ok and list(restored) == ["INBOX"] and restored["INBOX"][0][0] == eid, f"found {restored}")
    return 0 if all(inbound.results) else 1


if __name__ == "__main__":
    sys.exit(main())
