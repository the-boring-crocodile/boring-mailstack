#!/usr/bin/env python3
"""Put a fresh calendar invitation (iTip REQUEST from tim) into ACCOUNT's Inbox.

    inject_invite.py ACCOUNT

Appends it over IMAP (stalwart.mailstack.local) and prints its UID, for
ics_accept.py. The event is two days ahead, 09:00-10:00 UTC, with a unique UID.
Accounts: DEMO_ACCOUNTS (the demo's seed-accounts.json).
"""
import datetime
import imaplib
import json
import os
import re
import ssl
import sys
import time
import uuid
from email.message import EmailMessage

account = sys.argv[1]
accounts = json.load(open(os.environ.get("DEMO_ACCOUNTS", "/a.json")))
address = accounts[account]["address"]
uid = f"browser-test-{uuid.uuid4().hex[:12]}"
now = datetime.datetime.now(datetime.timezone.utc)
start = (now + datetime.timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
stamp = lambda d: d.strftime("%Y%m%dT%H%M%SZ")
ics = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//boring-mailstack//browser test//EN", "METHOD:REQUEST",
    "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp(now)}", f"DTSTART:{stamp(start)}",
    f"DTEND:{stamp(start + datetime.timedelta(hours=1))}", "SUMMARY:Browser test invitation", "SEQUENCE:0",
    "ORGANIZER;CN=Tim:mailto:tim@pond.test",
    f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{address}",
    "END:VEVENT", "END:VCALENDAR", ""])
m = EmailMessage()
m["From"] = "Tim <tim@pond.test>"
m["To"] = address
m["Subject"] = "Invitation: Browser test invitation"
m["Message-ID"] = f"<{uid}@pond.test>"
m.set_content("Please accept.")
m.add_alternative(ics, subtype="calendar", params={"method": "REQUEST"})

c = imaplib.IMAP4_SSL("stalwart.mailstack.local", 993, ssl_context=ssl._create_unverified_context())
c.login(accounts[account]["address"], accounts[account]["password"])
typ, data = c.append("INBOX", None, imaplib.Time2Internaldate(time.time()), m.as_bytes())
c.logout()
# The new UID from the APPEND answer (UIDPLUS): a search right after the
# APPEND may not see the message yet (Stalwart indexes asynchronously).
found = re.search(rb"APPENDUID \d+ (\d+)", data[0] or b"") if typ == "OK" and data else None
if not found:
    sys.exit(f"inject_invite: APPEND gave no UID: {typ} {data!r}")
print(found[1].decode())
