"""Manual lab check (not part of run.sh): with and without a reachable Nextcloud.

Run against a KEEP=1 acceptance demo, once with its demo-cloud container stopped
(expect: no Calendar/Files/Talk, "From cloud" and "Save all" hidden) and once
running (all shown):
  docker run --rm --network boring-mailstack-acceptance_webmail \\
    -v $PWD/tests/browser/no_cloud_manual.py:/p.py:ro -v DEMO/seed-accounts.json:/a.json:ro \\
    --entrypoint python3 boring-mailstack-browser /p.py
"""
import json
from playwright.sync_api import sync_playwright
ACC = json.load(open("/a.json")); U = "otter"; P = ACC[U]["password"]
vis = lambda pg, sel: [e.is_visible() for e in pg.query_selector_all(sel)]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1400, "height": 900})
    pg.goto("http://roundcube/"); pg.fill("#rcmloginuser", ACC[U]["address"]); pg.fill("#rcmloginpwd", P); pg.click("#rcmloginsubmit")
    pg.wait_for_selector("#taskmenu a.mail", timeout=30000)
    print("taskbar visible:", [a.get_attribute("class").split()[0] for a in pg.query_selector_all("#taskmenu a") if a.is_visible()])
    pg.goto("http://roundcube/?_task=mail&_action=compose"); pg.wait_for_selector("#compose-attachments", timeout=30000)
    pg.wait_for_timeout(1500)
    print("compose 'From cloud' visible:", vis(pg, "#compose-attachments button.attach.cloud"))
    import imaplib, email
    m = imaplib.IMAP4_SSL("stalwart.mailstack.local", 993, ssl_context=__import__("ssl")._create_unverified_context()); m.login(ACC[U]["address"], P); m.select("INBOX")
    uid = None
    for u in m.uid("search", None, "ALL")[1][0].split()[::-1]:
        bs = m.uid("fetch", u, "(BODYSTRUCTURE)")[1][0].decode(errors="replace")
        if "attachment" in bs.lower():
            uid = u.decode(); break
    print("message with attachment uid", uid)
    pg.goto(f"http://roundcube/?_task=mail&_action=show&_uid={uid}&_mbox=INBOX"); pg.wait_for_timeout(4000)
    print("page title", pg.title())
    pg.wait_for_timeout(1500)
    print("uid", uid, "attachments:", len(pg.query_selector_all(".attachmentslist li")), "message Save all visible:", vis(pg, "#message-header a.filesaveall"), "| attachment menu entry visible:", vis(pg, "#attachmenusaveas"))
    b.close()
