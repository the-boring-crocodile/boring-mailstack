#!/usr/bin/env python3
"""Browser check: a calendar invitation shows Kolab's invitation box with
Roundav active (cf. https://github.com/nicofrand/Roundav/issues/6).

    ics_invitation.py USER UID MAILBOX SCREENSHOT.jpg

Logs in to Roundcube (http://roundcube/) as USER, opens the mail, and
reports: invitation box present, RSVP buttons visible, the menu entries
of the attached invite.ics, and any JavaScript errors or warnings. Exit 0
only if the box and the buttons are there, the menu offers both "Save to
calendar" (Kolab) and "Save to cloud" (Roundav), and nothing was logged.
Accounts: DEMO_ACCOUNTS (the demo's seed-accounts.json).
"""
import json
import os
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

user, uid, box, shot = sys.argv[1:5]
accounts = json.load(open(os.environ.get("DEMO_ACCOUNTS", "/a.json")))
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    page.goto("http://roundcube/?_task=login")
    page.fill("#rcmloginuser", accounts[user]["address"])
    page.fill("#rcmloginpwd", accounts[user]["password"])
    page.click("#rcmloginsubmit")
    page.wait_for_selector("#mailboxlist", timeout=30000)

    page.goto(f"http://roundcube/?_task=mail&_action=show&_uid={uid}&_mbox="
              + urllib.parse.quote(box), wait_until="domcontentloaded")
    page.wait_for_selector(".calendar-invitebox", timeout=30000)
    page.wait_for_timeout(3000)    # the RSVP status loads by AJAX

    invitebox = page.locator(".calendar-invitebox").count()
    buttons = page.locator(".rsvp-buttons").first.is_visible()
    # The menu of the attached invite.ics (Elastic adds the toggle by script).
    item = page.locator("#attachment-list li", has_text="invite.ics").first
    item.locator("a.drop, a.dropdown").first.click()
    page.wait_for_timeout(800)
    menu = [x.inner_text().strip() for x in page.locator("#attachmentmenu li, #attachmentmenu-menu li").all()
            if x.is_visible()]
    page.screenshot(path=shot, type="jpeg", quality=55,
                    clip={"x": 0, "y": 0, "width": 1400, "height": 620})
    browser.close()

print(f"invitation box: {invitebox}; RSVP buttons visible: {buttons}")
print(f"attachment menu: {menu}")
print(f"JavaScript errors/warnings: {errors}")
both = any("calendar" in m.lower() for m in menu) and any("cloud" in m.lower() for m in menu)
print(f"Save to calendar and Save to cloud both offered: {both}")
sys.exit(0 if invitebox and buttons and both and not errors else 1)
