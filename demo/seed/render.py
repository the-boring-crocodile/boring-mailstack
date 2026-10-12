"""Render story mails (demo/story) into RFC 5322 messages.

Deterministic apart from the anchor time: the same story and the same
`now` always give the same bytes. Message-IDs are derived from story ids,
so threads link up across mailboxes exactly as they would in real life.
"""
import base64
import mimetypes
from datetime import datetime, timedelta, timezone
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

MSGID_DOMAIN = "lighthouse.pond.test"


def message_id(story_id):
    return f"<{story_id}@{MSGID_DOMAIN}>"


def anchor_times(now, tz):
    """Map a story day/time ('-92 08:47') to an aware datetime.

    Day 0 is the day of seeding; times are local times in `tz`."""
    today = now.astimezone(tz).date()

    def at(day, hour, minute):
        d = today + timedelta(days=day)
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
    return at


def _addr(cast, key):
    if key in cast["lists"]:
        lst = cast["lists"][key]
        name, address = lst["name"], lst["address"]
    else:
        person = cast["people"][key]
        name, address = person["name"], person["address"]
    user, domain = address.split("@", 1)
    return Address(display_name=name, username=user, domain=domain)


def _ancestors(mail, by_id):
    chain, seen = [], set()
    parent = by_id.get(mail.reply_to) if mail.reply_to else None
    while parent is not None and parent.id not in seen:
        seen.add(parent.id)
        chain.append(parent.id)
        parent = by_id.get(parent.reply_to) if parent.reply_to else None
    return list(reversed(chain))


def _subject(cast, mail):
    if not mail.list:
        return mail.subject
    tag = cast["lists"][mail.list].get("tag")
    if not tag or tag in mail.subject:
        return mail.subject
    if mail.subject.startswith("Re: "):
        return f"Re: {tag} {mail.subject[4:]}"
    return f"{tag} {mail.subject}"


def _ics(cast, mail, at):
    inv = mail.invite
    day, hm = inv["start"].split(" ")
    hour, minute = (int(x) for x in hm.split(":"))
    start = at(int(day), hour, minute).astimezone(timezone.utc)
    end = start + timedelta(minutes=int(inv.get("minutes", 30)))
    stamp = at(mail.day, mail.hour, mail.minute).astimezone(timezone.utc)
    fmt = "%Y%m%dT%H%M%SZ"
    organizer = cast["people"][mail.sender]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Pond Ltd//Office of Strategic Vision//EN",
        f"METHOD:{inv['method']}",
        "BEGIN:VEVENT",
        f"UID:{inv['uid']}@{MSGID_DOMAIN}",
        f"SEQUENCE:{int(inv.get('sequence', 0))}",
        f"DTSTAMP:{stamp.strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{inv['title']}",
        f"ORGANIZER;CN={organizer['name']}:mailto:{organizer['address']}",
    ]
    for key in mail.to + mail.cc:
        person = cast["people"][key]
        lines.append(f"ATTENDEE;CN={person['name']};RSVP=TRUE:mailto:{person['address']}")
    lines.append("STATUS:CANCELLED" if inv["method"] == "CANCEL" else "STATUS:CONFIRMED")
    lines += ["END:VEVENT", "END:VCALENDAR", ""]
    return "\r\n".join(lines)


QUOTE_DEPTH = 4   # nested quotes kept, as people trim deep threads


def _has_own_quote(body):
    return any(line.startswith(">") for line in body.splitlines())


def _sender_line(cast, key):
    p = cast["people"][key]
    return f"{p['name']} <{p['address']}>"


def text_with_history(cast, mail, by_id, at, depth=0):
    """The body as it appears in the mail, with the conversation below it.

    A reply quotes its parent as a mail client would on "Reply" (the
    parent's own quotes nest inside). Where the author quoted selectively
    ("> " lines in the story), that choice stands. Auto-replies don't quote.
    """
    body = mail.body
    parent = by_id.get(mail.reply_to) if mail.reply_to else None
    if parent is None or mail.auto_reply or _has_own_quote(body) or depth >= QUOTE_DEPTH:
        return body
    when = at(parent.day, parent.hour, parent.minute)
    head = f"On {when.strftime('%a, %d %b %Y')} at {when.strftime('%H:%M')}, {_sender_line(cast, parent.sender)} wrote:"
    quoted = text_with_history(cast, parent, by_id, at, depth + 1).rstrip("\n")
    lines = [("> " + l) if l else ">" for l in quoted.splitlines()]
    return body.rstrip("\n") + "\n\n" + head + "\n" + "\n".join(lines) + "\n"


def render(cast, mail, by_id, at, attachments_dir):
    """Return the message for `mail` as bytes (CRLF line endings)."""
    msg = EmailMessage(policy=policy.SMTP)
    msg["From"] = _addr(cast, mail.sender)
    msg["To"] = [_addr(cast, k) for k in mail.to]
    if mail.cc:
        msg["Cc"] = [_addr(cast, k) for k in mail.cc]
    msg["Subject"] = _subject(cast, mail)
    msg["Date"] = format_datetime(at(mail.day, mail.hour, mail.minute))
    msg["Message-ID"] = message_id(mail.id)
    ancestors = _ancestors(mail, by_id)
    if ancestors:
        msg["In-Reply-To"] = message_id(ancestors[-1])
        msg["References"] = " ".join(message_id(a) for a in ancestors)
    if mail.auto_reply:
        msg["Auto-Submitted"] = "auto-replied"
    body = text_with_history(cast, mail, by_id, at)
    if mail.list:
        lst = cast["lists"][mail.list]
        msg["List-Id"] = lst["list_id"]
        msg["List-Post"] = f"<mailto:{lst['address']}>"
        user, domain = lst["address"].split("@", 1)
        msg["List-Unsubscribe"] = f"<mailto:{user}-leave@{domain}>"
        msg["Precedence"] = "list"
        footer = mail.footer or lst.get("footer") or ""
        if footer:
            body = body.rstrip("\n") + "\n\n-- \n" + footer.rstrip("\n") + "\n"
    msg["X-Demo-Story"] = f"Operation Lighthouse; {mail.episode}; {mail.id}"
    msg.set_content(body, charset="utf-8")
    if mail.html:
        # A designed mail (the Services' adverts): the body above is its
        # plain-text part, the file in story/html/ its HTML part.
        html = (Path(attachments_dir).parent / "html" / mail.html).read_text(encoding="utf-8")
        msg.add_alternative(html, subtype="html", charset="utf-8")

    if mail.invite is not None:
        ics = _ics(cast, mail, at)
        msg.add_alternative(ics, subtype="calendar", charset="utf-8",
                            params={"method": mail.invite["method"]})
        msg.add_attachment(ics.encode("utf-8"), maintype="application",
                           subtype="ics", filename="invite.ics")
    for name in mail.attach:
        data = (Path(attachments_dir) / name).read_bytes()
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if name.endswith(".md"):
            ctype = "text/markdown"
        maintype, subtype = ctype.split("/", 1)
        if maintype == "text":
            msg.add_attachment(data.decode("utf-8"), subtype=subtype,
                               charset="utf-8", filename=name)
        else:
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return msg.as_bytes()


# --- IMAP folder names: modified UTF-7 (RFC 3501 §5.1.3) ------------------

def mutf7_encode(name):
    out, buf = [], []

    def flush():
        if buf:
            raw = "".join(buf).encode("utf-16-be")
            out.append("&" + base64.b64encode(raw).decode().rstrip("=").replace("/", ",") + "-")
            buf.clear()

    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)


# The same codec lives in getmail/folders.py and mail-provenance/provenance.py:
# separate images.
def mutf7_decode(name):
    out, i = [], 0
    while i < len(name):
        if name[i] == "&":
            j = name.index("-", i)
            if j == i + 1:
                out.append("&")
            else:
                b64 = name[i + 1:j].replace(",", "/")
                b64 += "=" * (-len(b64) % 4)
                out.append(base64.b64decode(b64).decode("utf-16-be"))
            i = j + 1
        else:
            out.append(name[i])
            i += 1
    return "".join(out)
