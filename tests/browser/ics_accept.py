#!/usr/bin/env python3
"""Browser check: accepting a calendar invitation saves it to the user's own
calendar.

    ics_accept.py ACCOUNT LOGIN UID MAILBOX SCREENSHOT.jpg [reply]

Logs in to Roundcube (http://roundcube/) with LOGIN (e.g. "otter", or the
full address "otter@pond.test": the webmail login then differs from the
Nextcloud user ID) and ACCOUNT's password, opens the invitation, checks that
a calendar to save to is offered, clicks Accept without sending a response,
and reports Roundcube's message. Exit 0 only if a calendar was offered and
the event was saved. With "reply": sends the response instead, and also
requires a copy of it (an iTip REPLY) in the account's Sent folder (IMAP,
stalwart.mailstack.local; calendar_itip_save_sent).
Accounts: DEMO_ACCOUNTS (the demo's seed-accounts.json).
"""
import imaplib
import json
import os
import ssl
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

account, login, uid, box, shot = sys.argv[1:6]
reply = sys.argv[6:7] == ["reply"]
accounts = json.load(open(os.environ.get("DEMO_ACCOUNTS", "/a.json")))
errors = []


def sent_replies():
    """iTip REPLY messages in the account's Sent folder (UIDs)."""
    c = imaplib.IMAP4_SSL("stalwart.mailstack.local", 993, ssl_context=ssl._create_unverified_context())
    c.login(accounts[account]["address"], accounts[account]["password"])
    found = set()
    for line in c.list()[1]:
        name = line.decode().rsplit(' "/" ', 1)[-1].strip('"')
        if "\\Sent" in line.decode() or name.split("/")[-1].split(".")[-1] == "Sent":
            if c.select(f'"{name}"', readonly=True)[0] == "OK":
                # A text/calendar part with method=REPLY (by structure: full-text
                # search for "METHOD:REPLY" depends on the server's tokenizer)
                typ, data = c.uid("FETCH", "1:*", "(BODYSTRUCTURE)")
                for item in data or []:
                    text = (item.decode(errors="replace") if isinstance(item, bytes) else "").lower()
                    if '"calendar"' in text and '"method" "reply"' in text:
                        found.add(f"{name}:" + text.split("uid ")[1].split()[0])
    c.logout()
    return found


before = sent_replies() if reply else set()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    page.goto("http://roundcube/?_task=login")
    page.fill("#rcmloginuser", login)
    page.fill("#rcmloginpwd", accounts[account]["password"])
    page.click("#rcmloginsubmit")
    page.wait_for_selector("#mailboxlist", timeout=30000)

    page.goto(f"http://roundcube/?_task=mail&_action=show&_uid={uid}&_mbox="
              + urllib.parse.quote(box), wait_until="domcontentloaded")
    page.wait_for_selector(".rsvp-buttons input.accepted", state="visible", timeout=30000)
    page.wait_for_timeout(1500)
    offered = [o.inner_text() for o in page.locator("#itip-saveto option").all()]
    # No response mail unless "reply": then the response and its Sent copy.
    toggle = page.locator("input[id^='noreply-']").first
    if toggle.count() and toggle.is_checked() == reply:
        toggle.set_checked(not reply, force=True)
    page.locator(".rsvp-buttons input.accepted").first.click()
    page.wait_for_selector("#messagestack div", timeout=30000)
    page.wait_for_timeout(1000)
    messages = [m.inner_text().strip() for m in page.locator("#messagestack div").all()]
    page.screenshot(path=shot, type="jpeg", quality=55,
                    clip={"x": 0, "y": 0, "width": 1400, "height": 620})
    browser.close()

saved = any("success" in m.lower() or "imported" in m.lower() or "saved" in m.lower()
            or "added" in m.lower() for m in messages)
print(f"login {login!r}: calendars offered {offered}")
print(f"messages: {messages}")
print(f"JavaScript errors: {errors}")
copied = True
if reply:
    page = None
    new = set()
    for _ in range(10):
        new = sent_replies() - before
        if new:
            break
        __import__("time").sleep(1)
    copied = bool(new)
    print(f"reply copies in Sent: {sorted(new)}")
sys.exit(0 if offered and saved and copied and not errors else 1)
