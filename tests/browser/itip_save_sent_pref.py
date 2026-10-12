#!/usr/bin/env python3
"""Browser check: the calendar preference "Save sent invitations and replies in
the Sent folder" (calendar_itip_save_sent) is shown and can be set.

    itip_save_sent_pref.py ACCOUNT on|off SCREENSHOT.jpg

Logs in, opens Settings > Preferences > Calendar, reports the checkbox state,
sets it to on/off, saves, reloads and exits 0 only if the saved state matches.
Accounts: DEMO_ACCOUNTS (the demo's seed-accounts.json).
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

account, want, shot = sys.argv[1], sys.argv[2] == "on", sys.argv[3]
accounts = json.load(open(os.environ.get("DEMO_ACCOUNTS", "/a.json")))

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://roundcube/?_task=login")
    page.fill("#rcmloginuser", accounts[account]["address"])
    page.fill("#rcmloginpwd", accounts[account]["password"])
    page.click("#rcmloginsubmit")
    page.wait_for_selector("#mailboxlist", timeout=30000)

    def form():
        page.goto("http://roundcube/?_task=settings&_action=edit-prefs&_section=calendar&_framed=1")
        box = page.locator("#rcmfd_itip_save_sent")
        box.wait_for(state="attached", timeout=30000)
        return box

    box = form()
    label = page.locator("label[for=rcmfd_itip_save_sent]").first.inner_text()
    before = box.is_checked()
    box.set_checked(want, force=True)
    set_now = box.is_checked()
    with page.expect_navigation():
        page.evaluate("rcmail.command('save')")  # as the Save button does
    after = form().is_checked()
    page.screenshot(path=shot, type="jpeg", quality=55)
    browser.close()

print(f"label: {label!r}; before: {before}; set: {set_now}; saved: {after}; wanted: {want}")
sys.exit(0 if after == want else 1)
