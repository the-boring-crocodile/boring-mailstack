#!/usr/bin/env python3
"""The provider's folder list (raw IMAP LIST from the scanner) for getmail
and the handoff.

    folders.py STATE_DIR CONFIG

Reads STATE_DIR/folders.list and writes, both atomically:
- STATE_DIR/folders.json: {folder name: {"role": special-use role or "",
  "delimiter": hierarchy separator or "", "selectable": bool}} — the
  handoff tells the bridge;
- STATE_DIR/getmail.rc: CONFIG with `mailboxes = ALL` replaced by the
  explicit folder list, INBOX first, without folders that cannot be selected,
  without views that only show mail filed elsewhere (special-use \\All,
  \\Important, \\Flagged: Gmail's "All Mail", "Important", "Starred") and
  without folders folders.yaml says to skip.
  INBOX first: a new mail reaches the filter before any label copy of it.

A folder's role: the first matching entry of CONFIG's rules file
(<account>.folders.json, from folders.yaml: [[folder pattern, role, origin],
...]), else its special-use flag, else none.

Fails (exit non-zero, nothing written) on a folder list it cannot read
completely (a LIST line it does not understand, no INBOX), a missing rules
file, or a CONFIG without `mailboxes = ALL`: a folder silently left out
would never be fetched.
"""
import base64
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

ROLES = {"\\junk": "junk", "\\sent": "sent", "\\drafts": "drafts",
         "\\trash": "trash", "\\archive": "archive", "\\all": "all",
         "\\important": "important", "\\flagged": "flagged"}
# Views of mail filed elsewhere, not placements, and what folders.yaml says
# to skip: never fetched.
NOT_FETCHED = {"all", "important", "flagged", "skip"}
LIST_RE = re.compile(r'^\* LIST \(([^)]*)\) (NIL|"(?:[^"\\]|\\.)*") (.*)$', re.I)


def mutf7_decode(name):
    """IMAP modified UTF-7 (RFC 3501 5.1.3) to str. The same codec lives in
    mail-provenance/provenance.py and demo/seed/render.py: separate images."""
    out, i = [], 0
    while i < len(name):
        if name[i] == "&":
            end = name.index("-", i)
            chunk = name[i + 1:end]
            if not chunk:
                out.append("&")
            else:
                b64 = chunk.replace(",", "/")
                b64 += "=" * (-len(b64) % 4)
                out.append(base64.b64decode(b64).decode("utf-16-be"))
            i = end + 1
        else:
            out.append(name[i])
            i += 1
    return "".join(out)


def unquote(value):
    if value.startswith('"') and value.endswith('"'):
        return re.sub(r'\\(.)', r'\1', value[1:-1])
    return value


def role_of(name, flag_role, rules):
    for pattern, role, _ in rules:
        if fnmatch.fnmatchcase(name, pattern):
            return "" if role == "none" else role
    return flag_role


def parse(lines, rules=()):
    folders = {}
    for line in lines:
        line = line.rstrip("\r\n")
        m = LIST_RE.match(line)
        if not m:
            if line.strip():
                raise ValueError(f"folder list line not understood: {line[:200]!r}")
            continue
        flags = {f.lower() for f in m.group(1).split()}
        delimiter = "" if m.group(2).upper() == "NIL" else unquote(m.group(2))
        name = mutf7_decode(unquote(m.group(3).strip()))
        if name.upper() == "INBOX":
            name = "INBOX"
        role = next((ROLES[f] for f in flags if f in ROLES), "")
        if name != "INBOX":
            role = role_of(name, role, rules)
        folders[name] = {"role": role, "delimiter": delimiter,
                         "selectable": not ({"\\noselect", "\\nonexistent"} & flags)}
    return folders


def write(path, text):
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def effective_rc(config_text, folders):
    m = re.search(r"^mailboxes\s*=\s*ALL\s*$", config_text, re.M)
    if not m:
        raise ValueError("the account's getmail config has no `mailboxes = ALL` (generate-config writes it)")
    names = tuple(n for n, f in sorted(folders.items(), key=lambda item: (item[0] != "INBOX", item[0]))
                  if f["selectable"] and f["role"] not in NOT_FETCHED)
    return config_text[:m.start()] + "mailboxes = " + repr(names) + config_text[m.end():]


def main(state_dir, config):
    state = Path(state_dir)
    try:
        rules = json.loads(Path(config).with_suffix(".folders.json").read_text(encoding="utf-8"))
        folders = parse((state / "folders.list").read_text(encoding="utf-8", errors="replace").splitlines(), rules)
        if "INBOX" not in folders:
            raise ValueError("no INBOX in the provider's folder list")
        rc = effective_rc(Path(config).read_text(encoding="utf-8"), folders)
    except (OSError, ValueError) as error:
        sys.exit(f"folders.py: {error}; nothing written")
    write(state / "folders.json", json.dumps(folders, indent=1, sort_keys=True) + "\n")
    write(state / "getmail.rc", rc)
    skipped = sorted(n for n, f in folders.items() if f["role"] in NOT_FETCHED)
    roles = sorted(f"{n}={f['role']}" for n, f in folders.items() if f["role"] and f["role"] not in NOT_FETCHED)
    print(f"FOLDERS {len(folders)}" + (f" (roles: {', '.join(roles)})" if roles else "")
          + (f" (not fetched: {', '.join(skipped)})" if skipped else ""))
    # Only for entries written for this account: a provider's entries need
    # not all exist in every mailbox there.
    for pattern, _, origin in rules:
        if origin == "account" and not any(fnmatch.fnmatchcase(n, pattern) for n in folders):
            print(f"FOLDER NOTE folders.yaml entry {pattern!r} matches no folder at the provider")


if __name__ == "__main__":
    main(*sys.argv[1:3])
