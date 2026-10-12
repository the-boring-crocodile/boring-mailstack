import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class YamlDiagnostics(unittest.TestCase):
    def test_no_source_excerpt_in_any_accounts_reader(self):
        token = "synthetic-" + "private-value"
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "accounts.yaml"
            config.write_text('password: "' + token + '" broken\n')
            for name in ("check-account-syntax", "check-account-connectivity", "generate-config"):
                module = script(name)
                module.CONFIG = config
                output = io.StringIO()
                with contextlib.redirect_stderr(output), contextlib.redirect_stdout(output), patch(
                    "subprocess.run", return_value=SimpleNamespace(returncode=0)
                ):
                    try:
                        status = module.main()
                    except SystemExit as exc:
                        status = exc.code
                self.assertTrue(status != 0)
                self.assertTrue(token not in output.getvalue(), name)
                self.assertTrue("accounts.yaml:1:" in output.getvalue(), name)
                self.assertTrue("ParserError" in output.getvalue(), name)


class ConfigValues(unittest.TestCase):
    def setUp(self):
        self.check = script("check-account-syntax")
        direction = dict(active=True, host="provider.test", port=993, tls="implicit",
                         username="person", password="synthetic-value")
        self.data = {"version": 1, "accounts": {"person": {
            "address": "person@example.test",
            "inbound": dict(direction),
            "outbound": dict(direction, port=465)}}}
        self.account = self.data["accounts"]["person"]

    def rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.check.validate(self.data)
        self.assertTrue("synthetic-value" not in str(caught.exception))

    def test_inbound_sieve_and_resieve_blocks(self):
        import accounts_yaml
        self.account["inbound_sieve"] = {"enabled": True, "folders": ["INBOX", "Junk"]}
        self.account["resieve"] = {"enabled": False, "never_move_from": ["Sent", "Drafts"]}
        self.check.validate(self.data)
        self.assertEqual(accounts_yaml.inbound_sieve_folders(self.account), ["INBOX", "Junk"])
        self.assertFalse(accounts_yaml.resieve_enabled(self.account))
        self.assertEqual(accounts_yaml.resieve_never_move_from(self.account), ["Sent", "Drafts"])
        self.account["inbound_sieve"] = {"enabled": False, "folders": ["INBOX"]}
        self.assertEqual(accounts_yaml.inbound_sieve_folders(self.account), [])
        for bad in ({"folders": "INBOX"}, {"enabled": "yes"}, {"other": 1}):
            self.account["inbound_sieve"] = bad
            self.rejected()
        self.account.pop("inbound_sieve")
        self.account["resieve"] = {"never_move_from": ["Sent,Drafts"]}
        self.rejected()

    def test_defaults_and_old_keys_refused(self):
        import accounts_yaml
        self.assertEqual(accounts_yaml.inbound_sieve_folders(self.account), ["INBOX"])
        self.assertTrue(accounts_yaml.resieve_enabled(self.account))
        self.assertIsNone(accounts_yaml.resieve_never_move_from(self.account))
        self.account["auto_resieve"] = False        # before v2026.10.14-rc.5
        self.rejected()
        self.account.pop("auto_resieve")
        self.account["inbound"]["folders"] = "ALL"  # before v2026.10.14-rc.6
        self.rejected()

    def test_address_has_one_at_with_both_sides(self):
        for bad in ("person@", "@example.test", "a@b@example.test", "person example@x.test", "person"):
            self.account["address"] = bad
            self.rejected()

    def test_controls_in_every_generated_string(self):
        for char in ("\r", "\n", "\t", "\0", "\x7f", "\x85"):
            for direction in ("inbound", "outbound"):
                for field in ("host", "username", "password"):
                    original = self.account[direction][field]
                    self.account[direction][field] = original + char
                    self.rejected()
                    self.account[direction][field] = original
            self.account["address"] = "person@example.test" + char
            self.rejected()
            self.account["address"] = "person@example.test"

    def test_credentials_whitespace_and_postfix_separator(self):
        for direction in ("inbound", "outbound"):
            for field in ("username", "password"):
                original = self.account[direction][field]
                for value in (" " + original, original + " "):
                    self.account[direction][field] = value
                    self.rejected()
                self.account[direction][field] = original
        self.account["outbound"]["username"] = "person:other"
        self.rejected()
        self.account["outbound"]["username"] = "person"
        self.account["inbound"]["username"] = "person:other"
        self.rejected()

    def test_inbound_sieve_folders_are_inbox_and_junk(self):
        self.account["inbound_sieve"] = {"folders": ["INBOX", "junk"]}
        self.check.validate(self.data)
        self.account["inbound_sieve"] = {"folders": ["INBOX", "Newsletter"]}
        with self.assertRaises(ValueError) as caught:
            self.check.validate(self.data)
        self.assertIn("only INBOX and Junk", str(caught.exception))

    def test_printable_credentials_are_preserved(self):
        for direction in ("inbound", "outbound"):
            self.account[direction]["password"] = 'synthetic-value:"\\#%'
        self.check.validate(self.data)

    def test_reserved_ids_are_refused(self):
        for reserved in ("mail-bridge", "admin", "postmaster"):
            data = {"version": 1, "accounts": {reserved: self.account}}
            with self.assertRaises(ValueError) as caught:
                self.check.validate(data)
            self.assertIn("reserved", str(caught.exception))

    def test_example_placeholder_is_refused(self):
        # accounts.example.yaml (and tools/setup's copy of it) say CHANGE-ME.
        self.assertIn("password: CHANGE-ME", (ROOT / "accounts.example.yaml").read_text())
        self.account["inbound"]["password"] = "CHANGE-ME"
        with self.assertRaises(ValueError) as caught:
            self.check.validate(self.data)
        self.assertIn("placeholder", str(caught.exception))

    def test_inactive_directions_are_also_checked(self):
        self.account["outbound"]["active"] = False
        self.account["outbound"]["password"] += "\n"
        self.rejected()


class FolderRules(unittest.TestCase):
    """folders.yaml (tools/accounts_yaml.py)."""

    def setUp(self):
        import accounts_yaml
        import yaml
        self.ay = accounts_yaml
        self.example = yaml.safe_load((ROOT / "folders.example.yaml").read_text())

    def test_example_is_valid_and_maps_hetzner(self):
        self.assertEqual(self.ay.folder_rules_errors(self.example, {"alice"}), [])
        rules = self.ay.folder_rules(self.example, "alice", "www123.your-server.de")
        self.assertIn(("INBOX.spambucket", "junk", "provider"), rules)
        self.assertEqual(self.ay.folder_rules(self.example, "bob", "imap.gmail.com"), [])

    def test_account_entries_come_first(self):
        data = {"version": 1, "providers": {"*.p.test": {"Spam": "junk"}, "*": {"X": "skip"}},
                "accounts": {"a": {"Spam": "none"}}}
        self.assertEqual(self.ay.folder_rules(data, "a", "IMAP.P.TEST"), [("Spam", "none", "account"), ("Spam", "junk", "provider")])
        self.assertEqual(self.ay.folder_rules(data, "b", "other.test"), [("X", "skip", "provider")])

    def test_errors(self):
        bad = {"version": 1, "providers": {"*": {"INBOX": "junk", "Spam": "spam"}},
               "accounts": {"ghost": {"A": "skip"}}, "extra": 1}
        errors = "\n".join(self.ay.folder_rules_errors(bad, {"alice"}))
        for expected in ("INBOX is always the inbox", "unknown role 'spam'", "accounts.ghost: no such account",
                         "unknown key 'extra'"):
            self.assertIn(expected, errors)
        self.assertTrue(self.ay.folder_rules_errors({"providers": {}}, set()))   # no version
