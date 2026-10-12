#!/usr/bin/env python3
"""Browser check: HTML mail in dark mode (plugin mailstack_darkmail).

    darkmail.py ACCOUNT OUTDIR

Puts three HTML mails into ACCOUNT's Inbox over IMAP: a plain one (no
backgrounds of its own, navy text, a white table, a picture), a designed one
(grey page, black button) and one with a picture in a cell that has a
background picture. In a browser that prefers dark mode:
  auto (default)  plain: dark background, navy text made light;
                  designed: stays white
  invert          plain: inverted (CSS filter), its picture turned back;
                  a picture in a cell with a background picture: turned
                  back once (the cell), not twice
  light mode      plain: as sent (navy stays navy)
Screenshots in OUTDIR. Accounts: DEMO_ACCOUNTS (seed-accounts.json).
"""
import imaplib
import json
import os
import re
import ssl
import sys
import time
import uuid
from email.message import EmailMessage

from playwright.sync_api import sync_playwright

account, out = sys.argv[1], sys.argv[2]
accounts = json.load(open(os.environ.get("DEMO_ACCOUNTS", "/a.json")))
tag = uuid.uuid4().hex[:8]

PLAIN = ('<p>Hello, this is a <b>plain</b> mail.</p>'
         '<p id="navy" style="color:#000080">Navy text from an old client.</p>'
         '<table bgcolor="#ffffff"><tr><td>A white table cell.</td></tr></table>'
         '<img id="picture" src="data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==" width="10" height="10">')
# A background picture makes a mail "designed"; this one is for 'invert'.
PICTURES = ('<table><tr><td id="bgcell" style="background-image:url(data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==)">'
            '<img id="inner" src="data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==" width="10" height="10"></td></tr></table>')
DESIGNED = ('<div style="background:#F5F7FA;padding:20px">'
            '<table><tr><td id="button" style="background-color:#000000;color:#ffffff;padding:10px">'
            'Open your account</td></tr></table></div>')


def put(subject, html):
    m = EmailMessage()
    m["From"] = "Sender <sender@outside.test>"
    m["To"] = accounts[account]["address"]
    m["Subject"] = f"{subject} {tag}"
    m["Message-ID"] = f"<{subject}.{tag}@darkmail.test>"
    m.set_content("text version")
    m.add_alternative(f"<html><body>{html}</body></html>", subtype="html")
    c = imaplib.IMAP4_SSL("stalwart.mailstack.local", 993, ssl_context=ssl._create_unverified_context())
    c.login(accounts[account]["address"], accounts[account]["password"])
    typ, data = c.append("INBOX", None, imaplib.Time2Internaldate(time.time()), m.as_bytes())
    c.logout()
    found = re.search(rb"APPENDUID \d+ (\d+)", data[0] or b"")
    if not found:
        sys.exit(f"darkmail: APPEND gave no UID: {typ} {data!r}")
    return found[1].decode()


plain_uid, designed_uid = put("Darkmail plain", PLAIN), put("Darkmail designed", DESIGNED)
pictures_uid = put("Darkmail pictures", PICTURES)
results = []


def check(name, ok, detail):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def look(page, uid, shot):
    page.goto(f"http://roundcube/?_task=mail&_action=show&_mbox=INBOX&_uid={uid}")
    page.wait_for_selector(".message-htmlpart", timeout=30000)
    page.wait_for_function("document.querySelector('.message-htmlpart').hasAttribute('data-mailstack-darkmail')"
                           " || !(window.rcmail && rcmail.env.mailstack_darkmail)", timeout=10000)
    page.screenshot(path=f"{out}/{shot}", type="jpeg", quality=55)
    return page.evaluate("""() => {
        const part = document.querySelector('.message-htmlpart'), cs = el => el && getComputedStyle(el);
        const navy = document.querySelector('.message-htmlpart [id$=navy]');
        const button = document.querySelector('.message-htmlpart [id$=button]');
        return {verdict: part.getAttribute('data-mailstack-darkmail'), dark: document.documentElement.classList.contains('dark-mode'),
                background: cs(part).backgroundColor, filter: cs(part).filter,
                navy: navy && cs(navy).color, button: button && cs(button).backgroundColor,
                picture: cs(document.querySelector('.message-htmlpart [id$=picture]'))?.filter,
                bgcell: cs(document.querySelector('.message-htmlpart [id$=bgcell]'))?.filter,
                inner: cs(document.querySelector('.message-htmlpart [id$=inner]'))?.filter};
    }""")


def set_mode(page, mode):
    page.goto("http://roundcube/?_task=settings&_action=edit-prefs&_section=mailview&_framed=1")
    select = page.locator("#rcmfd_mailstack_darkmail")
    select.wait_for(state="attached", timeout=30000)
    select.select_option(mode)
    with page.expect_navigation():
        page.evaluate("rcmail.command('save')")


def light(color):
    nums = [int(x) for x in re.findall(r"\d+", color or "")[:3]]
    return len(nums) == 3 and sum(nums) / 3 > 140


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1400, "height": 900}, color_scheme="dark")
    page = context.new_page()
    page.goto("http://roundcube/?_task=login")
    page.fill("#rcmloginuser", accounts[account]["address"])
    page.fill("#rcmloginpwd", accounts[account]["password"])
    page.click("#rcmloginsubmit")
    page.wait_for_selector("#mailboxlist", state="attached", timeout=30000)

    plain = look(page, plain_uid, "darkmail-plain-dark.jpg")
    check("dark mode, plain mail darkened", plain["dark"] and plain["verdict"] == "dark"
          and plain["background"] in ("rgba(0, 0, 0, 0)", "transparent") and light(plain["navy"]), plain)
    designed = look(page, designed_uid, "darkmail-designed-dark.jpg")
    check("dark mode, designed mail stays white", designed["verdict"] == "designed"
          and designed["background"] == "rgb(255, 255, 255)" and designed["button"] == "rgb(0, 0, 0)", designed)

    set_mode(page, "invert")
    inverted = look(page, plain_uid, "darkmail-plain-invert.jpg")
    check("setting 'invert': plain mail inverted, its picture turned back", inverted["verdict"] == "invert"
          and "invert" in inverted["filter"] and "invert" in (inverted["picture"] or ""), inverted)
    pictures = look(page, pictures_uid, "darkmail-pictures-invert.jpg")
    check("setting 'invert': a picture in a background-picture cell is turned back once",
          "invert" in (pictures["bgcell"] or "") and pictures["inner"] == "none", pictures)
    set_mode(page, "auto")

    page.emulate_media(color_scheme="light")
    lit = look(page, plain_uid, "darkmail-plain-light.jpg")
    check("light mode, plain mail as sent", not lit["dark"] and lit["navy"] == "rgb(0, 0, 128)", lit)
    browser.close()

sys.exit(0 if all(results) else 1)
