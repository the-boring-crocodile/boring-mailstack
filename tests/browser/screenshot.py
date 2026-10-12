"""The README screenshot (docs/screenshot.png), from a running demo.

    screenshot.py OUTFILE

Otter's mailbox in dark mode, every folder expanded, the provider's Junk
open, newest first, with Dr. Mallard's advert (story e6-s1, an HTML mail
with its own colours, which darkmail leaves as designed). Run it like the
other browser checks (README.md), with /a.json the demo's
seed-accounts.json:

    docker run --rm --network <demo project>_webmail \\
        -v "$PWD/tests/browser:/t:ro" -v "<demo dir>/seed-accounts.json:/a.json:ro" \\
        -v "$PWD/docs:/out" --entrypoint python3 boring-mailstack-browser \\
        /t/screenshot.py /out/screenshot.png
"""
import json
import sys

from playwright.sync_api import sync_playwright

out = sys.argv[1]
otter = json.load(open("/a.json"))["otter"]
SUBJECT = "TIRED of UNREAD MAIL?"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark").new_page()
    page.goto("http://roundcube/?_task=login")
    page.fill("#rcmloginuser", otter["address"])
    page.fill("#rcmloginpwd", otter["password"])
    page.click("#rcmloginsubmit")
    page.wait_for_selector("#mailboxlist")
    while page.locator("#mailboxlist div.treetoggle.collapsed").count():
        page.locator("#mailboxlist div.treetoggle.collapsed").first.click()
        page.wait_for_timeout(150)
    page.click("#mailboxlist li.junk > a")
    page.wait_for_selector(f"#messagelist tr:has-text('{SUBJECT}')")
    if page.evaluate("() => rcmail.env.sort_order") != "DESC":
        page.evaluate("() => rcmail.command('sort', rcmail.env.sort_col || 'date')")
        page.wait_for_timeout(1500)
    page.click(f"#messagelist tr:has-text('{SUBJECT}')")
    page.mouse.move(1000, 880)  # no hover toolbar on the selected row
    page.frame_locator("#messagecontframe").locator(".message-htmlpart").wait_for()
    page.wait_for_timeout(1500)
    state = page.evaluate("""() => ({
        dark: document.documentElement.classList.contains('dark-mode'),
        verdict: document.querySelector('#messagecontframe').contentDocument
                 .querySelector('.message-htmlpart').getAttribute('data-mailstack-darkmail'),
        collapsed: document.querySelectorAll('#mailboxlist div.treetoggle.collapsed').length})""")
    if not (state["dark"] and state["verdict"] == "designed" and state["collapsed"] == 0):
        sys.exit(f"screenshot: unexpected state {state}")
    page.screenshot(path=out)
    browser.close()
print(f"screenshot: {out} {state}")
