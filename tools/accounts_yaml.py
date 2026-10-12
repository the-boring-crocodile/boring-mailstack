"""Safe diagnostics for accounts.yaml (never include source excerpts)."""
import fnmatch


def yaml_error(path, exc):
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    location = f"{path}:{mark.line + 1}:{mark.column + 1}" if mark else str(path)
    return f"{location}: invalid YAML ({type(exc).__name__})"


# Effective per-account settings (defaults applied). accounts.yaml:
#   inbound_sieve: {enabled: true, folders: [INBOX]}   provider folders whose
#       fetched mail goes through the account's filter
#   resieve: {enabled: true, never_move_from: [...]}    re-sorting after a
#       filter change; never_move_from absent: resieve's own default
DEFAULT_SIEVE_FOLDERS = ["INBOX"]


def inbound_sieve_folders(account):
    """Provider folders delivered through the filter ([] when disabled)."""
    cfg = account.get("inbound_sieve") or {}
    if not cfg.get("enabled", True):
        return []
    return list(cfg.get("folders", DEFAULT_SIEVE_FOLDERS))


def resieve_enabled(account):
    return bool((account.get("resieve") or {}).get("enabled", True))


def resieve_never_move_from(account):
    """The configured list, or None for resieve's default."""
    cfg = account.get("resieve") or {}
    return list(cfg["never_move_from"]) if "never_move_from" in cfg else None


# folders.yaml: what each provider folder is, where the provider does not
# say it itself (RFC 6154 special-use flags) or says something else.
#   providers: {"<inbound host pattern>": {"<folder or pattern>": role}}
#   accounts:  {"<account id>":           {"<folder or pattern>": role}}
# An account's entries come before its provider's; within one list the first
# matching folder pattern counts (fnmatch: * ? [..]); a folder no entry
# matches keeps the role from its special-use flag.
FOLDER_ROLES = {
    "sent", "drafts", "junk", "trash", "archive",   # placements
    "all", "important", "flagged",                  # views: not fetched
    "skip",                                         # not fetched
    "none",                                         # an ordinary folder
}


def folder_rules_errors(data, account_ids):
    """Problems in a parsed folders.yaml, as messages (empty: valid)."""
    errors = []
    if not isinstance(data, dict) or data.get("version") != 1:
        return ["folders.yaml: expected a mapping with version: 1"]
    for key in data:
        if key not in ("version", "providers", "accounts"):
            errors.append(f"folders.yaml: unknown key {key!r}")
    for section in ("providers", "accounts"):
        entries = data.get(section) or {}
        if not isinstance(entries, dict):
            errors.append(f"folders.yaml: {section} must be a mapping")
            continue
        for owner, rules in entries.items():
            where = f"folders.yaml: {section}.{owner}"
            if section == "accounts" and owner not in account_ids:
                errors.append(f"{where}: no such account in accounts.yaml")
            if not isinstance(rules, dict) or not rules:
                errors.append(f"{where}: expected folder: role entries")
                continue
            for folder, role in rules.items():
                if not isinstance(folder, str) or not folder:
                    errors.append(f"{where}: folder names must be text")
                elif folder.upper() == "INBOX":
                    errors.append(f"{where}: INBOX is always the inbox")
                if role not in FOLDER_ROLES:
                    errors.append(f"{where}.{folder}: unknown role {role!r} "
                                  f"(one of {', '.join(sorted(FOLDER_ROLES))})")
    return errors


def folder_rules(data, account_id, host):
    """[(folder pattern, role, "account" or "provider"), ...] for one
    account, in the order they count: the account's entries, then those of
    the first provider pattern matching its inbound host."""
    rules = [(folder, role, "account")
             for folder, role in ((data.get("accounts") or {}).get(account_id) or {}).items()]
    for pattern, entries in (data.get("providers") or {}).items():
        if fnmatch.fnmatchcase(host.lower(), pattern.lower()):
            rules += [(folder, role, "provider") for folder, role in entries.items()]
            break
    return rules
