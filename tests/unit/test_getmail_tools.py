"""Unit tests for getmail/folders.py and getmail/handoff.py (no network)."""
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "getmail" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


folders = load("folders")
handoff = load("handoff")

LIST = [
    '* LIST (\\HasNoChildren) "." INBOX',
    '* LIST (\\HasNoChildren \\Junk) "." "INBOX.Spam"',
    '* LIST (\\HasNoChildren \\Sent) "." "Sent Items"',
    '* LIST (\\Noselect \\HasChildren) "/" "[Gmail]"',
    '* LIST (\\HasNoChildren \\All) "/" "[Gmail]/All Mail"',
    '* LIST (\\HasNoChildren \\Important) "/" "[Gmail]/Important"',
    '* LIST (\\HasNoChildren \\Flagged) "/" "[Gmail]/Starred"',
    '* LIST (\\HasNoChildren) "/" "Archive"',
    '* LIST (\\HasNoChildren) "." "Gran&AQE-s"',
    '* LIST (\\HasNoChildren) NIL "Flat \\"quoted\\""',
]


class Folders(unittest.TestCase):
    def test_parse(self):
        f = folders.parse(LIST)
        self.assertEqual(f["INBOX.Spam"], {"role": "junk", "delimiter": ".", "selectable": True})
        self.assertEqual(f["Sent Items"]["role"], "sent")
        self.assertFalse(f["[Gmail]"]["selectable"])
        self.assertEqual(f["[Gmail]/All Mail"]["role"], "all")
        self.assertIn("Granās", f)
        self.assertEqual(f['Flat "quoted"']["delimiter"], "")

    def test_rc_without_all_mail_view(self):
        rc = "[retriever]\nmailboxes = ALL\n[options]\ndelete = false\n"
        out = folders.effective_rc(rc, folders.parse(LIST))
        line = [l for l in out.splitlines() if l.startswith("mailboxes")][0]
        names = eval(line.split("=", 1)[1])
        self.assertIn("INBOX.Spam", names)
        self.assertNotIn("[Gmail]/All Mail", names)
        self.assertNotIn("[Gmail]/Important", names)   # views of mail filed elsewhere
        self.assertNotIn("[Gmail]/Starred", names)
        self.assertNotIn("[Gmail]", names)
        self.assertEqual(names[0], "INBOX")             # before "Archive": the filter first
        self.assertTrue(out.endswith("delete = false\n"))

    def test_refuses_what_it_cannot_read_completely(self):
        # A folder left out silently would never be fetched.
        with self.assertRaises(ValueError):
            folders.parse(LIST + ['* LIST (\\HasNoChildren) "/" {11}', 'Folder name'])   # an IMAP literal
        with self.assertRaises(ValueError):
            folders.effective_rc("mailboxes = ('INBOX',)\n", folders.parse(LIST))

    def test_rules_from_folders_yaml(self):
        hetzner = ['* LIST () "." INBOX', '* LIST () "." INBOX.Sent', '* LIST () "." INBOX.spambucket',
                   '* LIST () "." INBOX.Werbung', '* LIST () "." INBOX.Werbung.Alt', '* LIST () "." INBOX.Projekt',
                   '* LIST (\\Junk) "." INBOX.Junk']
        rules = [["INBOX.Werbung*", "skip", "account"], ["INBOX.Sent", "sent", "provider"], ["INBOX.spambucket", "junk", "provider"],
                 ["INBOX.Junk", "none", "account"], ["INBOX", "junk", "account"]]
        f = folders.parse(hetzner, rules)
        self.assertEqual(f["INBOX.Sent"]["role"], "sent")
        self.assertEqual(f["INBOX.spambucket"]["role"], "junk")
        self.assertEqual(f["INBOX.Projekt"]["role"], "")          # no rule, no flag: a folder
        self.assertEqual(f["INBOX.Junk"]["role"], "")             # "none" overrides the flag
        self.assertEqual(f["INBOX"]["role"], "")                  # INBOX is never remapped
        rc = folders.effective_rc("mailboxes = ALL\n", f)
        names = eval(rc.split("=", 1)[1])
        self.assertNotIn("INBOX.Werbung", names)                  # skip
        self.assertNotIn("INBOX.Werbung.Alt", names)
        self.assertIn("INBOX.spambucket", names)

    def test_rules_file_next_to_the_config(self):
        d = Path(tempfile.mkdtemp())
        (d / "folders.list").write_text('* LIST () "." INBOX\n* LIST () "." INBOX.Sent\n')
        (d / "acc.conf").write_text("mailboxes = ALL\n")
        (d / "acc.folders.json").write_text(json.dumps([["INBOX.Sent", "sent", "provider"],
                                                        ["Nothing", "trash", "account"],
                                                        ["INBOX.Trash", "trash", "provider"]]))
        out = io.StringIO()
        saved, sys.stdout = sys.stdout, out
        try:
            folders.main(str(d), str(d / "acc.conf"))
        finally:
            sys.stdout = saved
        self.assertEqual(json.loads((d / "folders.json").read_text())["INBOX.Sent"]["role"], "sent")
        self.assertIn("roles: INBOX.Sent=sent", out.getvalue())
        self.assertIn("'Nothing' matches no folder", out.getvalue())
        self.assertNotIn("INBOX.Trash", out.getvalue())          # a provider entry: no note


class Handoff(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp())
        handoff.STATE = self.state
        (self.state / "croc").mkdir()
        (self.state / "croc" / "folders.json").write_text(json.dumps(
            {"INBOX": {"role": "", "delimiter": "."}, "INBOX.Spam": {"role": "junk", "delimiter": "."}}))
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        handoff.BRIDGE = self.server.getsockname()
        self.received = []

    def tearDown(self):
        self.server.close()

    def serve(self, answer):
        def run():
            conn, _ = self.server.accept()
            data = b""
            while chunk := conn.recv(4096):
                data += chunk
            self.received.append(data)
            conn.sendall(answer)
            conn.close()
        t = threading.Thread(target=run)
        t.start()
        return t

    def call(self, *args, message=b"Subject: x\n\nbody\n"):
        saved = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(message))
        try:
            return handoff.main(*args)
        finally:
            sys.stdin = saved

    def test_fields_sent(self):
        t = self.serve(b"OK\n")
        self.assertEqual(self.call("croc", "INBOX.Spam", "unknown"), 0)
        t.join()
        self.assertEqual(self.received[0], b"ACCOUNT:croc\nMAILBOX:INBOX.Spam\nSENDER:\nDELIMITER:.\n"
                         b"ROLE:junk\n\nSubject: x\n\nbody\n")
        self.assertEqual(list(self.state.glob(".handoff-*")), [])

    def test_labels_announced_for_a_provider_with_all_mail(self):
        (self.state / "croc" / "folders.json").write_text(json.dumps(
            {"INBOX": {"role": "", "delimiter": "/"}, "Work": {"role": "", "delimiter": "/"},
             "[Gmail]/All Mail": {"role": "all", "delimiter": "/"}}))
        t = self.serve(b"OK\n")
        self.assertEqual(self.call("croc", "Work", "a@b"), 0)
        t.join()
        self.assertIn(b"\nLABELS:yes\n\n", self.received[0])

    def test_error_is_temporary(self):
        t = self.serve(b"ERROR\n")
        self.assertEqual(self.call("croc", "INBOX", "a@b"), 75)
        t.join()

    def test_folder_not_in_the_list_waits(self):
        # Without the folder list the bridge would not know the separator or
        # the role: the mail stays at the provider for the next pass.
        self.assertEqual(self.call("croc", "Unlisted", "a@b"), 75)
        (self.state / "croc" / "folders.json").unlink()
        self.assertEqual(self.call("croc", "INBOX", "a@b"), 75)

    def test_stopping_defers(self):
        (self.state / ".stopping").touch()
        self.assertEqual(self.call("croc", "INBOX", "a@b"), 75)


if __name__ == "__main__":
    unittest.main()
