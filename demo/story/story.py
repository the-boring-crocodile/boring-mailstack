#!/usr/bin/env python3
"""Read the Operation Lighthouse story files and check them.

    python3 demo/story/story.py check      # validate; exit 1 on any error
    python3 demo/story/story.py stats      # mails per mailbox and folder

The seeder imports `load()` and `deliveries()` from here, so the rules the
check enforces are the rules the demo is built from.
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
EPISODES = HERE / "episodes"
ATTACHMENTS = HERE / "attachments"
HTML = HERE / "html"
DAY_RE = re.compile(r"^(-\d+) (\d{2}):(\d{2})$")
HEADER_KEYS = {
    "id", "day", "from", "to", "cc", "subject", "reply_to", "folder",
    "attach", "list", "invite", "footer", "auto_reply", "html",
}
INVITE_KEYS = {"method", "uid", "title", "start", "minutes", "sequence"}
RULE_KEYS = {"folder", "from", "involves", "list", "invite", "to_self", "subject_has", "ids"}


@dataclass
class Mail:
    id: str
    episode: str
    day: int
    hour: int
    minute: int
    sender: str
    to: list
    cc: list
    subject: str
    body: str
    reply_to: str | None = None
    folder: dict = field(default_factory=dict)
    attach: list = field(default_factory=list)
    list: str | None = None
    invite: dict | None = None
    footer: str | None = None
    auto_reply: bool = False
    html: str | None = None

    @property
    def when(self):
        """Sort key: (day, minutes past midnight)."""
        return (self.day, self.hour * 60 + self.minute)


def parse_day(value, where):
    m = DAY_RE.match(str(value))
    if not m:
        raise ValueError(f"{where}: day must look like '-92 08:47', got {value!r}")
    day, hour, minute = int(m[1]), int(m[2]), int(m[3])
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"{where}: impossible time {value!r}")
    return day, hour, minute


def parse_episode(path):
    text = path.read_text(encoding="utf-8")
    # Everything before the first separator is the episode's introduction.
    blocks = re.split(r"^===\s*$", text, flags=re.M)[1:]
    mails = []
    for n, block in enumerate(blocks, 1):
        where = f"{path.name} block {n}"
        m = re.match(r"\s*^---\s*$\n(.*?)^---\s*$\n?(.*)\Z", block, flags=re.M | re.S)
        if not m:
            raise ValueError(f"{where}: missing '---' header")
        head = yaml.safe_load(m[1]) or {}
        unknown = set(head) - HEADER_KEYS
        if unknown:
            raise ValueError(f"{where}: unknown header keys {sorted(unknown)}")
        missing = {"id", "from", "subject"} - set(head)
        if missing:
            raise ValueError(f"{where}: missing header keys {sorted(missing)}")
        day, hour, minute = parse_day(head.get("day"), where)
        mails.append(Mail(
            id=str(head["id"]),
            episode=path.stem,
            day=day, hour=hour, minute=minute,
            sender=head["from"],
            to=list(head.get("to") or []),
            cc=list(head.get("cc") or []),
            subject=str(head["subject"]),
            body=m[2].strip("\n") + "\n",
            reply_to=head.get("reply_to"),
            folder=dict(head.get("folder") or {}),
            attach=list(head.get("attach") or []),
            list=head.get("list"),
            invite=head.get("invite"),
            footer=head.get("footer"),
            auto_reply=bool(head.get("auto_reply", False)),
            html=head.get("html"),
        ))
    return mails


def load():
    cast = yaml.safe_load((HERE / "characters.yaml").read_text(encoding="utf-8"))
    cast["filing"] = yaml.safe_load((HERE / "filing.yaml").read_text(encoding="utf-8")) or {}
    mails = []
    for path in sorted(EPISODES.glob("*.md")):
        mails.extend(parse_episode(path))
    mails.sort(key=lambda m: m.when)
    return cast, mails


def mailboxes(cast):
    return [k for k, p in cast["people"].items() if p.get("mailbox")]


def rule_matches(rule, box, mail):
    people = [mail.sender, *mail.to, *mail.cc]
    tests = {
        "from": lambda v: mail.sender in v,
        "involves": lambda v: any(k in v for k in people),
        "list": lambda v: mail.list == v,
        "invite": lambda v: (mail.invite is not None) == bool(v),
        "to_self": lambda v: (mail.sender == box and box in mail.to) == bool(v),
        "subject_has": lambda v: any(w.lower() in mail.subject.lower() for w in v),
        "ids": lambda v: mail.id in v,
    }
    return all(tests[k](v) for k, v in rule.items() if k != "folder")


def file_for(cast, box, mail, folder):
    """Apply the owner's filing habits to mail that would land in INBOX."""
    if folder != "INBOX":
        return folder
    for rule in cast["filing"].get(box) or []:
        if rule_matches(rule, box, mail):
            return rule["folder"]
    return folder


def deliveries(cast, mail):
    """{mailbox: folder} for every demo mailbox that holds a copy of `mail`.

    The folder is where the mail sits at the provider before the first
    import, after the owner's filing habits (filing.yaml)."""
    boxes = set(mailboxes(cast))
    out = {}
    recipients = mail.to + mail.cc
    for key in recipients:
        if key in cast["lists"]:
            targets = cast["lists"][key]["members"]
        else:
            targets = [key]
        for t in targets:
            if t in boxes and t != mail.sender:
                out[t] = mail.folder.get(t, "INBOX")
    if mail.sender in boxes:
        # A mail to oneself (Otter's prediction log) is in Inbox and Sent.
        out[mail.sender] = "Sent" if mail.sender not in recipients else "INBOX"
    return {box: file_for(cast, box, mail, f) for box, f in out.items()}


def check(cast, mails):
    errors = []
    people, lists = cast["people"], cast["lists"]
    known = set(people) | set(lists)
    boxes = set(mailboxes(cast))
    by_id = {}

    for m in mails:
        where = f"{m.episode}/{m.id}"
        if m.id in by_id:
            errors.append(f"{where}: duplicate id")
        by_id[m.id] = m
        for k in [m.sender, *m.to, *m.cc]:
            if k not in known:
                errors.append(f"{where}: unknown person or list {k!r}")
        if m.sender in lists:
            errors.append(f"{where}: a list cannot be the sender")
        if not m.to:
            errors.append(f"{where}: no recipients")
        for box, folder in m.folder.items():
            if box not in boxes:
                errors.append(f"{where}: folder for {box!r}, which has no mailbox")
            if folder not in {"INBOX", "Junk", "Sent"}:
                errors.append(f"{where}: header folders are INBOX, Junk or Sent; "
                              f"personal folders belong in filing.yaml")
        for name in m.attach:
            if not (ATTACHMENTS / name).is_file():
                errors.append(f"{where}: attachment {name!r} missing")
        if m.html is not None:
            if not (HTML / str(m.html)).is_file():
                errors.append(f"{where}: html {m.html!r} missing")
            if m.reply_to or m.list or m.invite is not None:
                errors.append(f"{where}: an html mail stands alone (no reply_to, list or invite)")
        if m.list:
            if m.list not in lists:
                errors.append(f"{where}: unknown list {m.list!r}")
            elif m.to != [m.list] or m.cc:
                errors.append(f"{where}: list post must go to [{m.list}] only")
        elif any(r in lists for r in m.to + m.cc):
            errors.append(f"{where}: mail to a list without `list:`")
        if m.footer and not m.list:
            errors.append(f"{where}: footer outside a list post")
        if m.invite is not None:
            unknown = set(m.invite) - INVITE_KEYS
            if unknown:
                errors.append(f"{where}: unknown invite keys {sorted(unknown)}")
            if m.invite.get("method") not in {"REQUEST", "CANCEL"}:
                errors.append(f"{where}: invite method must be REQUEST or CANCEL")
            try:
                parse_day(m.invite.get("start"), where)
            except ValueError as exc:
                errors.append(str(exc))
        if not deliveries(cast, m):
            errors.append(f"{where}: no demo mailbox ever sees this mail")

    for box, rules in cast["filing"].items():
        if box not in boxes:
            errors.append(f"filing.yaml: {box!r} has no mailbox")
        for n, rule in enumerate(rules or [], 1):
            where = f"filing.yaml {box} rule {n}"
            if set(rule) - RULE_KEYS or "folder" not in rule or len(rule) < 2:
                errors.append(f"{where}: needs `folder` and at least one known match key")
            for key in ("from", "involves"):
                for k in rule.get(key, []):
                    if k not in known:
                        errors.append(f"{where}: unknown person {k!r}")
            if "list" in rule and rule["list"] not in lists:
                errors.append(f"{where}: unknown list {rule['list']!r}")
            if rule.get("folder") in {"INBOX", "Junk", "Sent"}:
                errors.append(f"{where}: filing into {rule['folder']} is not filing")
            if not any(deliveries(cast, m).get(box) == rule["folder"] for m in mails):
                errors.append(f"{where}: rule files nothing (shadowed or no match)")

    for m in mails:
        where = f"{m.episode}/{m.id}"
        if not m.reply_to:
            continue
        parent = by_id.get(m.reply_to)
        if parent is None:
            errors.append(f"{where}: reply_to {m.reply_to!r} does not exist")
            continue
        if parent.when > m.when:
            errors.append(f"{where}: replies to {parent.id}, which is later")
        # Perspective rule: a mailbox can only reply to what it has.
        if m.sender in boxes and m.sender not in deliveries(cast, parent):
            errors.append(f"{where}: {m.sender} replies to {parent.id} without having it")
    return errors


def stats(cast, mails):
    counts = {}
    for m in mails:
        for box, folder in deliveries(cast, m).items():
            counts.setdefault(box, {}).setdefault(folder, 0)
            counts[box][folder] += 1
    print(f"{len(mails)} mails in {len({m.episode for m in mails})} episodes")
    for box in mailboxes(cast):
        folders = counts.get(box, {})
        detail = ", ".join(f"{f} {n}" for f, n in sorted(folders.items()))
        print(f"  {box:6} {sum(folders.values()):4}  ({detail})")


def main(argv):
    cast, mails = load()
    if argv[1:] == ["check"]:
        errors = check(cast, mails)
        for e in errors:
            print("ERROR", e)
        print(f"{len(mails)} mails, {len(errors)} errors")
        return 1 if errors else 0
    if argv[1:] == ["stats"]:
        stats(cast, mails)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
