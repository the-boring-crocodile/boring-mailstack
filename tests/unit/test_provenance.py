"""Unit tests for mail-provenance's event handling (no Stalwart, no IMAP)."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("provenance", ROOT / "mail-provenance" / "provenance.py")
prov = importlib.util.module_from_spec(_spec)
sys.modules["provenance"] = prov
_spec.loader.exec_module(prov)


class Directory:
    def find_by_login_name(self, name):
        return {"id": name} if name else None


class FakeImap:
    def __init__(self, entries):
        self.entries = entries

    def list(self):
        return "OK", self.entries


class ListParsing(unittest.TestCase):
    def test_quoted_escaped_atom_and_literal_names(self):
        entries = [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren) "/" "Say \\"hi\\""',
            b'(\\HasNoChildren) "/" Archive',
            (b'(\\HasNoChildren) "/" {7}', b'Lit"eral'),
            b")",
            b"garbage that does not parse",
        ]
        self.assertEqual(prov.list_mailboxes(FakeImap(entries)),
                         ["INBOX", 'Say "hi"', "Archive", 'Lit"eral'])


class Events(unittest.TestCase):
    def setUp(self):
        self.telemetry = prov.TelemetryMappings(Directory())
        self.calls = []

    def run_events(self, events, handlers):
        saved = {name: getattr(prov, name) for name in handlers}
        try:
            for name, fn in handlers.items():
                setattr(prov, name, fn)
            return prov.handle_events(self.telemetry, None, events)
        finally:
            for name, fn in saved.items():
                setattr(prov, name, fn)

    def test_mappings_first_then_each_event_on_its_own(self):
        def move(telemetry, store, event, reason="imap-move"):
            account, name = telemetry.resolve_move_destination(2, 13)
            self.calls.append((reason, name))
            if event["data"].get("bad"):
                raise RuntimeError("uid vanished")
        events = [
            {"type": "imap.move", "data": {"bad": True}},
            {"type": "imap.copy", "data": {}},
            {"type": "imap.create-mailbox", "data": {"accountId": 2, "mailboxId": [13], "mailboxName": "New"}},
        ]
        retry = self.run_events(events, {"handle_move": move})
        self.assertFalse(retry)                     # a permanent failure is skipped
        self.assertEqual(self.calls, [("imap-move", "New"), ("imap-copy", "New")])

    def test_transient_failure_asks_for_a_retry(self):
        def move(telemetry, store, event, reason="imap-move"):
            raise OSError("connection refused")
        self.assertTrue(self.run_events([{"type": "imap.move", "data": {}}], {"handle_move": move}))

    def test_rename_updates_the_name(self):
        self.run_events([
            {"type": "imap.select", "data": {"accountId": 2, "mailboxId": 13, "mailboxName": "Old"}},
            {"type": "imap.rename-mailbox", "data": {"accountId": 2, "mailboxId": 13, "mailboxName": "Renamed"}},
        ], {})
        self.assertEqual(self.telemetry.resolve_move_destination(2, 13)[1], "Renamed")

    def test_unknown_mailbox_relearns_once_and_retries(self):
        prov._relearned.clear()
        self.telemetry.remember_account({"accountId": 2, "accountName": "croc"})
        learned = []
        event = {"type": "imap.move", "data": {"accountId": 2, "mailboxId": 99, "uid": [1]}}
        handlers = {"bootstrap_account": lambda account: learned.append(account["id"])}
        self.assertTrue(self.run_events([event], handlers))
        self.assertTrue(self.run_events([event], handlers))   # still retried ...
        self.assertEqual(learned, ["croc"])                    # ... but examined once a minute

    def test_move_into_inbox_goes_back_to_the_filter(self):
        notified = []
        self.telemetry.remember_account({"accountId": 2, "accountName": "croc"})
        self.telemetry.remember_mailbox({"accountId": 2, "mailboxId": 1, "mailboxName": "INBOX"})
        self.telemetry.remember_mailbox({"accountId": 2, "mailboxId": 5, "mailboxName": "Bank"})

        class Store:
            def protect(self, *args):
                pass

        saved = (prov.RESORT_URL, prov.fetch_email_ids, prov.notify_resort, prov.junk_folder)
        try:
            prov.RESORT_URL = "http://watch/resort"
            # UID 8 is gone meanwhile: 7 and 9 are still recorded.
            prov.fetch_email_ids = lambda account, mailbox, uids: {u: f"e{u}" for u in uids if u != 8}
            prov.notify_resort = lambda account, ids: notified.append((account, ids))
            prov.junk_folder = lambda account: "Junk Mail"
            prov.handle_move(self.telemetry, Store(), {"data": {"accountId": 2, "mailboxId": 1, "uid": [7, 8, 10]}})
            prov.handle_move(self.telemetry, Store(), {"data": {"accountId": 2, "mailboxId": 5, "uid": [9]}})
        finally:
            prov.RESORT_URL, prov.fetch_email_ids, prov.notify_resort, prov.junk_folder = saved
        self.assertEqual(notified, [("croc", ["e7", "e10"])])


if __name__ == "__main__":
    unittest.main()
