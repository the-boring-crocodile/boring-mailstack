#!/usr/bin/env python3
"""Live checks on a running demo (see tests/demo/run.sh).

1. Round trip: croc submits a mail to Stalwart addressed to
   otter@pond.test. It must leave through the relay, arrive at otter's
   (demo) provider, and be fetched back into otter's Stalwart Inbox.
2. Webmail: brog logs in to Roundcube (session written to its database),
   opens Filters (Roundcube logs in to Stalwart's ManageSieve as brog) and
   the Contacts settings (RCMCardDAV).
3. Human move: tim moves a mail from his Inbox into "Networking 🤝" over
   IMAP, as Roundcube would. Provenance must record it.
4. Cloud: otter logs in for the first time. The demo's Pond Cloud preset
   gives him Contacts (autocomplete finds a colleague from it), Calendar
   (his seeded appointments; a new one lands in Pond Cloud) and cloud
   files (Roundav lists, creates a folder, saves a mail's attachment
   there), all with his webmail login via mailstack_cloudfiles.
5. Isolation: the mail containers cannot reach the Internet.
"""
import base64
import datetime
import http.cookiejar
import imaplib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import os
import email.policy
import email.utils
import smtplib
import socket
import sqlite3
import ssl
import sys
import time
import uuid
from email.message import EmailMessage
from pathlib import Path

HOST = os.environ.get("STALWART_HOST", "stalwart.mailstack.local")
CTX = ssl._create_unverified_context()  # demo Stalwart: self-signed
ACCOUNTS = json.loads(Path(os.environ["DEMO_ACCOUNTS"]).read_text())
PROVENANCE_DB = os.environ["PROVENANCE_DB"]
results = []


def check(name, ok, detail):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def imap(user):
    c = imaplib.IMAP4_SSL(HOST, 993, ssl_context=CTX)
    c.login(ACCOUNTS[user]["address"], ACCOUNTS[user]["password"])
    return c


def search_subject(c, mailbox, marker):
    c.select(mailbox, readonly=True)
    typ, data = c.search(None, "SUBJECT", f'"{marker}"')
    return data[0].split() if typ == "OK" else []


def to_oneself():
    """Mail to one's own address, sent as Roundcube does: submitted over SMTP
    and the same bytes appended to Sent. The arriving copy is identical to
    the Sent copy and must still land in the Inbox (found in daily use, 2026-10-09)."""
    marker = f"To myself {uuid.uuid4().hex[:10]}"
    msg = EmailMessage()
    msg["From"] = "Croc <croc@pond.test>"
    msg["To"] = "Croc <croc@pond.test>"
    msg["Subject"] = f"Note to self — {marker}"
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain="pond.test")
    msg.set_content("Buy beans.\n")
    t0 = time.time()
    with smtplib.SMTP_SSL(HOST, 465, context=CTX, timeout=30) as s:
        s.login(ACCOUNTS["croc"]["address"], ACCOUNTS["croc"]["password"])
        s.send_message(msg)
    c = imap("croc")
    sent = next('"' + m[1] + '"' for line in c.list()[1]
                if (m := re.search(r'\\Sent\b.*? "(?:[^"]*)" "?([^"]*)"?$', line.decode())))
    try:
        c.append(sent, "(\\Seen)", None, msg.as_bytes(policy=email.policy.SMTP))
        while time.time() - t0 < 180:
            if search_subject(c, "INBOX", marker):
                kept = bool(search_subject(c, sent, marker))
                check("mail to oneself", kept, f"in croc's Inbox after {time.time() - t0:.0f}s"
                      + ("; Sent copy kept" if kept else "; Sent copy GONE"))
                return
            time.sleep(3)
    finally:
        c.logout()
    check("mail to oneself", False, "not in croc's Inbox after 180s (the Sent copy taken for it?)")


def roundtrip():
    marker = f"Roundtrip {uuid.uuid4().hex[:10]}"
    msg = EmailMessage()
    msg["From"] = "Croc <croc@pond.test>"
    msg["To"] = "Otter <otter@pond.test>"
    msg["Subject"] = f"Re: Lighthouse — {marker}"
    msg.set_content("Otter, a quick test that mail really goes round.\n\nCroc\n☕ 1 today\n")
    t0 = time.time()
    with smtplib.SMTP_SSL(HOST, 465, context=CTX, timeout=30) as s:
        s.login(ACCOUNTS["croc"]["address"], ACCOUNTS["croc"]["password"])
        s.send_message(msg)
    c = imap("otter")
    try:
        while time.time() - t0 < 180:
            if search_subject(c, "INBOX", marker):
                check("round trip", True, f"croc -> relay -> provider -> getmail -> otter's Inbox in {time.time() - t0:.0f}s")
                return
            time.sleep(3)
    finally:
        c.logout()
    check("round trip", False, "not in otter's Inbox after 180s")


def webmail_login():
    jar = http.cookiejar.CookieJar()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)
    base = os.environ.get("ROUNDCUBE_URL", "http://roundcube/")
    page = opener.open(base + "?_task=login", timeout=20).read().decode()
    token = re.search(r'name="_token" value="([^"]+)"', page)[1]
    data = urllib.parse.urlencode({"_token": token, "_task": "login", "_action": "login",
                                   "_timezone": "Europe/London", "_user": ACCOUNTS["brog"]["address"],
                                   "_pass": ACCOUNTS["brog"]["password"]}).encode()
    try:
        r = opener.open(base + "?_task=login", data=data, timeout=30)
        status, location = r.status, r.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        status, location = e.code, e.headers.get("Location", "")
    ok = status == 302 and "_task=mail" in location
    check("webmail login", ok, f"brog -> HTTP {status} {location[:40]}")
    if not ok:
        return

    def page(query):
        try:
            with opener.open(base + query, timeout=30) as r:
                return r.status, r.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, ""

    # Filters: the plugin connects and logs in to ManageSieve for this page;
    # on failure the page still renders, with one of these messages.
    status, html = page("?_task=settings&_action=plugin.managesieve")
    errors = [m for m in ("Unable to connect to server", "Unknown server error",
                          "filterconnerror", "filterunknownerror") if m in html]
    ok = status == 200 and 'id="filtersetslist"' in html and not errors
    check("webmail filters", ok, f"brog -> Filters HTTP {status}"
          + (", ManageSieve login ok" if ok else f", errors {errors}"))

    status, html = page("?_task=settings&_action=plugin.carddav")
    ok = status == 200 and "carddav" in html.lower()
    check("webmail contacts", ok, f"brog -> CardDAV settings HTTP {status}")


class Webmail:
    """A Roundcube session, as a browser would hold it."""

    def __init__(self, user):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        self.base = os.environ.get("ROUNDCUBE_URL", "http://roundcube/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect)
        page = self.get("?_task=login")[2]
        token = re.search(r'name="_token" value="([^"]+)"', page)[1]
        status, headers, _ = self.get("?_task=login", {
            "_token": token, "_task": "login", "_action": "login", "_timezone": "Europe/London",
            "_user": ACCOUNTS[user]["address"], "_pass": ACCOUNTS[user]["password"]})
        self.ok = status == 302 and "_task=mail" in headers.get("Location", "")
        self.html = self.get("?_task=mail")[2] if self.ok else ""
        m = re.search(r'"request_token":"([^"]+)"', self.html)
        self.token = m[1] if m else ""

    def get(self, query, form=None, ajax=False):
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        headers = {"X-Roundcube-Request": self.token, "X-Requested-With": "XMLHttpRequest"} if ajax else {}
        req = urllib.request.Request(self.base + query, data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=60) as r:
                return r.status, r.headers, r.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode(errors="replace")


def cloud(user="otter", routine="Risk register review"):
    w = Webmail(user)
    check("cloud login", w.ok and w.token != "", f"{user} -> webmail")
    if not w.ok:
        return
    check("cloud calendar button", "#taskmenu a.button-calendar," not in w.html,
          "shown (Pond Cloud account from the demo preset)")
    links = {}
    for tag in re.findall(r'<a [^>]*button-nc-[^>]*>', w.html):
        name, href = re.search(r'button-nc-(\w+)', tag), re.search(r'href="([^"]+)"', tag)
        if name and href:
            links[name[1]] = href[1]
    check("cloud task bar links", links.get("files", "").endswith("/apps/files/")
          and links.get("talk", "").endswith("/apps/spreed/"), f"{links}")

    # Contacts: the preset addressbook syncs and autocomplete finds TIM.
    _, _, r = w.get("?_task=mail&_action=autocomplete&_search=tim&_reqid=1", ajax=True)
    check("cloud contacts", "tim@pond.test" in r and "carddav" in r,
          "autocomplete finds TIM in the Pond Cloud addressbook")

    # Calendar: the seeded calendar and appointments.
    status, _, html = w.get("?_task=calendar")
    i = html.find('"calendars":')
    cals = json.JSONDecoder().raw_decode(html[i + 12:])[0] if i >= 0 else {}
    cal = next((k for k, v in (cals.items() if isinstance(cals, dict) else []) if v.get("name") == "Personal"), None)
    check("cloud calendar", status == 200 and cal is not None, f"HTTP {status}, calendars {list(cals)[:3]}")
    names = {v.get("name"): bool(v.get("default")) for v in (cals.values() if isinstance(cals, dict) else [])}
    check("cloud default calendar", names.get("Personal") is True and names.get("Projects") is False,
          f"Nextcloud's default marked: {names}")
    if cal:
        monday = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
        rng = f"start={monday}T00:00:00&end={monday + datetime.timedelta(days=7)}T00:00:00"
        _, _, r = w.get(f"?_task=calendar&_action=load_events&source={cal}&{rng}", ajax=True)
        titles = {e.get("title") for e in json.loads(r)} if r.startswith("[") else set()
        check("cloud appointments", {"Pond stand-up", routine} <= titles,
              f"this week: {sorted(titles)}")

        title = f"Acceptance {uuid.uuid4().hex[:8]}"
        day = datetime.date.today() + datetime.timedelta(days=1)
        _, _, r = w.get("?_task=calendar&_action=event", {
            "_remote": "1", "action": "new", "e[calendar]": cal, "e[title]": title,
            "e[start]": f"{day}T10:00:00", "e[end]": f"{day}T10:30:00", "e[allDay]": "0"}, ajax=True)
        check("cloud new appointment", title in cloud_calendar(user),
              f"{title!r} saved in {user}'s Pond Cloud calendar")

    # Files: Roundav sees Pond Cloud, lists and creates folders.
    api = "?_task=roundav&_action=roundav_api&method="
    _, _, r = w.get(api + "folder_list&flat=true", ajax=True)
    folders = json.loads(r).get("result", {}).get("folders", []) if r.startswith("{") else []
    _, _, r = w.get(api + "file_list&folder=Documents", ajax=True)
    files = [f.get("name") for f in (json.loads(r).get("result") or {}).values()] if r.startswith("{") else []
    check("cloud files", "Files/Documents" in folders and "Office handbook.txt" in files,
          f"folders {folders}, Documents {files}")
    name = f"Acceptance {uuid.uuid4().hex[:8]}"
    _, _, r = w.get(api + "folder_create", {"folder": f"Files/{name}"}, ajax=True)
    check("cloud files write", name in cloud_list(user, f"files/{user}/"), f"folder {name!r} created in Pond Cloud")

    # Save to cloud: a story mail's attachment into the new folder.
    found = attachment_mail(user)
    if not found:
        check("cloud save attachment", False, f"no mail with an attachment in {user}'s mailbox")
        return
    mailbox, uid, filename = found
    w.get("?_task=mail&_action=plugin.roundav", {
        "_mbox": mailbox, "_uid": uid, "act": "save_file", "uid": uid,
        "dest": f"Files/{name}", "id": "", "name": ""}, ajax=True)
    saved = cloud_list(user, f"files/{user}/{urllib.parse.quote(name)}/")
    check("cloud save attachment", filename in saved,
          f"{filename!r} from {mailbox} saved to Pond Cloud folder {name!r}")


def attachment_mail(user):
    """(mailbox, uid, filename) of the user's first mail with a named attachment."""
    c = imap(user)
    try:
        for line in c.list()[1]:
            mailbox = line.decode().rsplit(' "/" ', 1)[-1].strip('"')
            if c.select(f'"{mailbox}"', readonly=True)[0] != "OK":
                continue
            typ, data = c.uid("FETCH", "1:*", "(BODYSTRUCTURE)")
            for item in data or []:
                text = item.decode(errors="replace") if isinstance(item, bytes) else ""
                m = re.search(r'"attachment" \("filename" "([^"]+)"', text, re.I)
                u = re.search(r"UID (\d+)", text)
                if m and u and "=?" not in m[1]:
                    return mailbox, u[1], m[1]
    finally:
        c.logout()
    return None


def cloud_request(user, method, path, depth="1"):
    auth = base64.b64encode(f"{user}:{ACCOUNTS[user]['password']}".encode()).decode()
    req = urllib.request.Request(f"http://cloud.pond.test:8080/remote.php/dav/{path}", method=method,
                                 headers={"Authorization": f"Basic {auth}", "Depth": depth})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode(errors="replace")


def cloud_list(user, path):
    return urllib.parse.unquote(cloud_request(user, "PROPFIND", path))


def cloud_calendar(user):
    """All appointments in the user's Pond Cloud calendar, as iCalendar text."""
    hrefs = re.findall(r"<d:href>([^<]+\.ics)</d:href>", cloud_request(user, "PROPFIND", f"calendars/{user}/personal/"))
    return "".join(cloud_request(user, "GET", h.split("/remote.php/dav/", 1)[1], "0") for h in hrefs)


def human_move():
    folder_wire = '"Networking &2D7dHQ-"'   # "Networking 🤝" in modified UTF-7
    con = sqlite3.connect(f"file:{PROVENANCE_DB}?mode=ro", uri=True)
    q = "select count(*) from protected_email where account='tim' and reason != 'provider-mailbox'"
    before = con.execute(q).fetchone()[0]
    c = imap("tim")
    try:
        c.select("INBOX")
        typ, data = c.uid("SEARCH", None, "ALL")
        uid = data[0].split()[-1].decode()
        typ, resp = c.uid("MOVE", uid, folder_wire)
        if typ != "OK":
            check("human move", False, f"IMAP MOVE failed: {resp}")
            return
    finally:
        c.logout()
    t0 = time.time()
    while time.time() - t0 < 60:
        after = con.execute(q).fetchone()[0]
        if after > before:
            check("human move", True, f"move into 'Networking 🤝' recorded by provenance ({before} -> {after})")
            return
        time.sleep(2)
    check("human move", False, "no provenance record 60s after the move")


def isolation():
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=4).close()
        check("isolation", False, "this container reached the Internet")
    except OSError as exc:
        check("isolation", True, f"no Internet from the mail network ({type(exc).__name__})")


if __name__ == "__main__":
    roundtrip()
    to_oneself()
    webmail_login()
    human_move()
    cloud()
    isolation()
    sys.exit(0 if all(results) else 1)
