#!/usr/bin/env python3
"""getmail's delivery command (MDA_external): hands one fetched mail to the
bridge.

    handoff.py ACCOUNT MAILBOX SENDER   (message on stdin)

Exit 0: the bridge stored it (getmail records it as fetched). Exit 75
(temporary failure): getmail keeps it and fetches it again later. From the
provider's folder list (folders.py, STATE/ACCOUNT/folders.json) the request
carries the folder's hierarchy separator (DELIMITER, NIL for none), its role
(ROLE, if any) and LABELS:yes when the provider's folders are labels. A
folder missing from that list is not handed over (exit 75): without it the
bridge would not know where the mail belongs.

While the container stops (STATE/.stopping exists) no new handover starts;
a running one is marked (STATE/.handoff-PID) so the stop waits for it.
"""
import json
import os
import socket
import sys
from pathlib import Path

STATE = Path("/state")
BRIDGE = ("mail-bridge", int(os.environ["MAILSTACK_BRIDGE_PORT"]))   # stack.env


def folder_info(account, mailbox):
    """(role, delimiter, labels): labels when the provider has an all-mail
    view (Gmail): there a folder is a label, a mail can carry several.
    LookupError when the folder list or the folder is missing."""
    try:
        folders = json.loads((STATE / account / "folders.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LookupError(f"no folder list for {account} ({error})")
    info = folders.get("INBOX" if mailbox.upper() == "INBOX" else mailbox)
    if info is None:
        raise LookupError(f"{mailbox!r} is not in {account}'s folder list")
    labels = any(f.get("role") == "all" for f in folders.values())
    return info["role"], info["delimiter"], labels


def main(account, mailbox, sender):
    if (STATE / ".stopping").exists():
        print("handoff deferred: stopping", file=sys.stderr)
        return 75
    marker = STATE / f".handoff-{os.getpid()}"
    marker.touch()
    try:
        message = sys.stdin.buffer.read()
        if sender == "unknown":   # getmail's word for "no envelope sender"
            sender = ""
        try:
            role, delimiter, labels = folder_info(account, mailbox)
        except LookupError as error:
            print(f"handoff deferred: {error}", file=sys.stderr)
            return 75
        head = f"ACCOUNT:{account}\nMAILBOX:{mailbox}\nSENDER:{sender}\nDELIMITER:{delimiter or 'NIL'}\n"
        if role:
            head += f"ROLE:{role}\n"
        if labels:
            head += "LABELS:yes\n"
        try:
            with socket.create_connection(BRIDGE, timeout=30) as s:
                s.settimeout(300)   # the bridge may wait for provenance
                s.sendall(head.encode("utf-8") + b"\n" + message)
                s.shutdown(socket.SHUT_WR)
                response = b""
                while chunk := s.recv(4096):
                    response += chunk
        except OSError as exc:
            print(f"handoff failed: bridge unavailable ({exc})", file=sys.stderr)
            return 75
        if response.strip() != b"OK":
            print(f"handoff failed: response=<{response.strip()[:200]!r}>", file=sys.stderr)
            return 75
        return 0
    finally:
        marker.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
