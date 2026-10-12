"""Unit tests for bridge/bridge.py: no network, no Docker.

    python3 -m unittest discover -s tests/unit
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_routes = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
json.dump({"croc": {"address": "croc@pond.test", "stalwart_user": "croc", "active": True,
                    "sieve_folders": ["INBOX"]}}, _routes)
_routes.close()
os.environ.update({
    "JMAP_SESSION": "https://stalwart.mailstack.local/jmap/session",
    "JMAP_USER": "bridge",
    "JMAP_PASSWORD": "unused",
    "PROVENANCE_URL": "http://provenance.invalid",
    "BRIDGE_ROUTES_FILE": _routes.name,
})
_spec = importlib.util.spec_from_file_location("bridge", ROOT / "bridge" / "bridge.py")
bridge = importlib.util.module_from_spec(_spec)
sys.modules["bridge"] = bridge
_spec.loader.exec_module(bridge)
os.unlink(_routes.name)

BODY = (b"Received: from mx.provider.test (mx.provider.test [192.0.2.1])\n"
        b"\tby provider; Tue, 6 Oct 2026 10:00:00 +0000\n"
        b"From: Tim <tim@pond.test>\nTo: croc@pond.test\nSubject: hello\n"
        b"Message-ID: <abc@pond.test>\n\nbody\n")


def fetched(ip, msgid, newline=b"\n"):
    """BODY as getmail delivers it: its own lines in front."""
    head = (b"Return-Path: <tim@pond.test>\nDelivered-To: croc@pond.test\n"
            b"Received: from mail.provider.test (" + ip + b":3993) by host with\n"
            b"  IMAP4-SSL getmail6 msgid:" + msgid + b"; 07 Oct 2026 06:52:48 -0000\n")
    return (head + BODY).replace(b"\n", newline)


class Routes(unittest.TestCase):
    def write(self, data):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        f.write(data if isinstance(data, str) else json.dumps(data))
        f.close()
        self.addCleanup(os.unlink, f.name)
        return Path(f.name)

    def test_valid(self):
        routes = bridge.load_routes(self.write(
            {"a": {"address": "a@x.test", "stalwart_user": "a", "active": False, "sieve_folders": ["INBOX"]}}))
        self.assertEqual(routes["a"].stalwart_user, "a")
        self.assertFalse(routes["a"].active)

    def test_sieve_folders(self):
        routes = bridge.load_routes(self.write(
            {"a": {"address": "a@x.test", "stalwart_user": "a", "active": True,
                   "sieve_folders": ["INBOX", "Junk"]},
             "b": {"address": "b@x.test", "stalwart_user": "b", "active": True, "sieve_folders": []}}))
        self.assertEqual(routes["a"].sieve_folders, frozenset({"inbox", "junk"}))
        self.assertEqual(routes["b"].sieve_folders, frozenset())
        with self.assertRaisesRegex(RuntimeError, "missing 'sieve_folders'"):    # generate-config writes it
            bridge.load_routes(self.write({"c": {"address": "c@x.test", "stalwart_user": "c", "active": True}}))

    def test_missing_key(self):
        with self.assertRaisesRegex(RuntimeError, "route 'a' missing 'stalwart_user'"):
            bridge.load_routes(self.write({"a": {"address": "a@x.test", "active": True}}))

    def test_empty_address(self):
        with self.assertRaisesRegex(RuntimeError, "empty address"):
            bridge.load_routes(self.write({"a": {"address": "", "stalwart_user": "a", "active": True, "sieve_folders": []}}))

    def test_empty_user(self):
        with self.assertRaisesRegex(RuntimeError, "empty Stalwart user"):
            bridge.load_routes(self.write({"a": {"address": "a@x.test", "stalwart_user": "", "active": True, "sieve_folders": []}}))

    def test_malformed_json(self):
        with self.assertRaises(ValueError):
            bridge.load_routes(self.write("{not json"))


class Config(unittest.TestCase):
    def test_missing_variable(self):
        saved = os.environ.pop("JMAP_USER")
        self.addCleanup(os.environ.__setitem__, "JMAP_USER", saved)
        with self.assertRaises(KeyError):
            bridge.load_config()

    def test_provenance_url_required(self):
        saved = os.environ.pop("PROVENANCE_URL")
        self.addCleanup(os.environ.__setitem__, "PROVENANCE_URL", saved)
        with self.assertRaises(KeyError):
            bridge.load_config()


class GetmailSource(unittest.TestCase):
    def test_two_fetches_same_source(self):
        a = fetched(b"172.26.0.2", b"1791355932/1")
        b = fetched(b"192.168.144.10", b"1791999999/17")
        self.assertNotEqual(len(a), len(b))
        self.assertEqual(bridge.getmail_source(a), bridge.getmail_source(b))
        self.assertEqual(bridge.getmail_source(a), BODY)

    def test_crlf(self):
        self.assertEqual(bridge.getmail_source(fetched(b"10.0.0.1", b"1/1", b"\r\n")),
                         BODY.replace(b"\n", b"\r\n"))

    def test_provider_received_kept(self):
        self.assertEqual(bridge.getmail_source(BODY), BODY)

    def test_other_body_differs(self):
        other = fetched(b"10.0.0.1", b"1/1").replace(b"body\n", b"other\n")
        self.assertNotEqual(bridge.getmail_source(other), bridge.getmail_source(fetched(b"10.0.0.1", b"1/1")))

    def test_message_id(self):
        self.assertEqual(bridge.source_message_id(fetched(b"10.0.0.1", b"1/1")), "abc@pond.test")


SESSION = bridge.JmapSession(account_id="a", api_url="http://api", upload_url="http://up",
                             download_url="http://down/{blobId}")


class Protocol(unittest.TestCase):
    def read(self, data):
        import io
        return bridge.read_delivery_request(io.BytesIO(data))

    def test_plain(self):
        r = self.read(b"ACCOUNT:a\nMAILBOX:INBOX\nSENDER:s@x.test\nDELIMITER:/\n\nbody")
        self.assertEqual((r.role, r.delimiter, r.labels), ("", "/", False))

    def test_delimiter_required_and_one_character(self):
        for head in (b"", b"DELIMITER:ab\n", b"DELIMITER:\n"):
            with self.assertRaises(bridge.ProtocolError):
                self.read(b"ACCOUNT:a\nMAILBOX:x\nSENDER:\n" + head + b"\nbody")

    def test_labels_field(self):
        req = self.read(b"ACCOUNT:a\nMAILBOX:Work\nSENDER:s@x.test\nDELIMITER:/\nLABELS:yes\n\nx")
        self.assertTrue(req.labels)
        with self.assertRaises(bridge.ProtocolError):
            self.read(b"ACCOUNT:a\nMAILBOX:Work\nSENDER:s@x.test\nDELIMITER:/\nLABELS:no\n\nx")

    def test_role_and_delimiter(self):
        r = self.read(b"ACCOUNT:a\nMAILBOX:Spam\nSENDER:\nROLE:junk\nDELIMITER:.\n\nbody")
        self.assertEqual((r.mailbox, r.role, r.delimiter), ("Spam", "junk", "."))
        # Roles are checked where they are written (folders.yaml, the
        # provider's marks); one the bridge has no use for changes nothing.
        r = self.read(b"ACCOUNT:a\nMAILBOX:x\nSENDER:\nROLE:weird\nDELIMITER:NIL\n\nbody")
        self.assertEqual((r.role, r.delimiter), ("weird", ""))

    def test_unknown_field(self):
        with self.assertRaisesRegex(bridge.ProtocolError, "unknown field 'FOO'"):
            self.read(b"ACCOUNT:a\nMAILBOX:x\nSENDER:\nDELIMITER:.\nFOO:1\n\nbody")
        with self.assertRaisesRegex(bridge.ProtocolError, "twice"):
            self.read(b"ACCOUNT:a\nMAILBOX:x\nSENDER:\nDELIMITER:.\nDELIMITER:.\n\nbody")


class Identity(unittest.TestCase):
    def test_message_id_kept(self):
        raw = fetched(b"1.1.1.1", b"1/1")
        self.assertIs(bridge.ensure_message_id(raw), raw)

    def test_message_id_made_up_deterministically(self):
        a = fetched(b"1.1.1.1", b"1/1").replace(b"Message-ID: <abc@pond.test>\n", b"")
        b = fetched(b"2.2.2.2", b"9/9").replace(b"Message-ID: <abc@pond.test>\n", b"")
        ida = bridge.source_message_id(bridge.ensure_message_id(a))
        self.assertTrue(ida.endswith("@mailstack.invalid"))
        self.assertEqual(ida, bridge.source_message_id(bridge.ensure_message_id(b)))

    def test_same_mail_through_other_paths(self):
        imported = fetched(b"1.1.1.1", b"1/1")
        via_smtp = (b"Received: from bridge by stalwart\r\nDelivered-To: croc@pond.test\r\n"
                    b"X-Spam-Status: No\r\n" + fetched(b"2.2.2.2", b"7/7", b"\r\n"))
        self.assertEqual(bridge.mail_identity(imported), bridge.mail_identity(via_smtp))

    def test_other_body_or_header_differs(self):
        raw = fetched(b"1.1.1.1", b"1/1")
        self.assertNotEqual(bridge.mail_identity(raw), bridge.mail_identity(raw.replace(b"body\n", b"other\n")))
        self.assertNotEqual(bridge.mail_identity(raw), bridge.mail_identity(raw.replace(b"Subject: hello", b"Subject: hi")))

    def test_junk_header_replaced(self):
        raw = b"X-Mailstack-Provider-Folder: Junk\n  forged\nFrom: a@x\n\nb"
        self.assertEqual(bridge.without_header(raw, bridge.JUNK_HEADER), b"From: a@x\n\nb")


class IndexJmap(bridge.JmapClient):
    def __init__(self):
        super().__init__(bridge.load_config())
        self.mails = {"e1": "m1", "e2": "m2"}
        self.state, self.changes = "s1", None

    def call(self, api_url, target_user, method, args):
        if method == "Email/get":
            ids = args["ids"]
            return {"state": self.state, "list": [{"id": i, "messageId": [self.mails[i]]} for i in ids]}
        if method == "Email/query":
            return {"ids": list(self.mails)[args["position"]:]}
        if method == "Email/changes":
            if self.changes == "gone":
                raise bridge.JmapError({"type": "cannotCalculateChanges"})
            return self.changes
        raise AssertionError(method)


class MessageIndex(unittest.TestCase):
    def test_load_and_follow_changes(self):
        j = IndexJmap()
        self.assertEqual(j.message_ids(SESSION, "u")["by_mid"], {"m1": {"e1"}, "m2": {"e2"}})
        j.mails["e3"] = "m1"
        j.changes = {"created": ["e3"], "destroyed": ["e2"], "newState": "s2", "hasMoreChanges": False}
        index = j.message_ids(SESSION, "u")
        self.assertEqual(index["by_mid"], {"m1": {"e1", "e3"}})
        self.assertEqual(index["state"], "s2")

    def test_reload_when_changes_unknown(self):
        j = IndexJmap()
        j.message_ids(SESSION, "u")
        j.changes = "gone"
        j.mails = {"e9": "m9"}
        self.assertEqual(j.message_ids(SESSION, "u")["by_mid"], {"m9": {"e9"}})


class Deliver(unittest.TestCase):
    """Which way a mail goes (bridge.deliver), with Stalwart faked."""

    def run_case(self, mailbox, same_id=None, identical=None, protected=(), role="",
                 target_role=None, sieve=("inbox",), roles=None, labels=False, keep_import=False):
        roles = {"T": target_role, **(roles or {})}
        log = []
        saved = {n: getattr(bridge, n) for n in
                 ("ROUTES", "same_mail_copies", "deliver_smtp", "provenance_protected",
                  "protect_provider_placement")}
        jsaved = {n: getattr(bridge.JMAP, n) for n in
                  ("with_session", "resolve_mailbox", "mailbox_role_of", "set_mailboxes", "import_new")}
        try:
            bridge.ROUTES = {"a": bridge.Route("a", "a@x.test", "a@x.test", True, frozenset(sieve))}
            bridge.same_mail_copies = lambda session, user, raw: (same_id or {}, identical or {})
            bridge.deliver_smtp = lambda raw, sender, address, junk=False: log.append(("smtp", junk))
            bridge.provenance_protected = lambda account, ids: set(protected) & set(ids)
            bridge.protect_provider_placement = lambda account, email_id: log.append(("protect", email_id))
            bridge.JMAP.with_session = lambda user, work: work(SESSION)
            bridge.JMAP.resolve_mailbox = lambda session, user, name, role, delimiter: "T"
            bridge.JMAP.mailbox_role_of = lambda session, user, mailbox_id: roles.get(mailbox_id)
            bridge.JMAP.set_mailboxes = lambda session, user, email_id, patch: log.append(("set", email_id, patch))
            if not keep_import:
                bridge.JMAP.import_new = lambda raw, target, session, user: log.append(("import", target)) or "new"
            result = bridge.deliver(bridge.DeliveryRequest("a", mailbox, "s@x.test", BODY, delimiter="/",
                                                           role=role, labels=labels))
        finally:
            for n, v in saved.items():
                setattr(bridge, n, v)
            for n, v in jsaved.items():
                setattr(bridge.JMAP, n, v)
        return result.method, log

    def test_inbox_new_mail_goes_through_the_filter(self):
        self.assertEqual(self.run_case("INBOX"), ("smtp", [("smtp", False)]))

    def test_provider_junk_goes_to_the_junk_port(self):
        self.assertEqual(self.run_case("Spam", role="junk", sieve=("inbox", "junk")),
                         ("smtp-junk", [("smtp", True)]))
        self.assertEqual(self.run_case("Junk", role="junk", sieve=("inbox", "junk")),
                         ("smtp-junk", [("smtp", True)]))

    def test_a_folder_named_junk_without_a_role_is_just_a_folder(self):
        # Roles come from the provider's flags or folders.yaml, never
        # from a name: a provider folder "Junk" without either is imported
        # as it is, like any folder (not filtered, not spam).
        self.assertEqual(self.run_case("Junk", sieve=("inbox", "junk")),
                         ("jmap", [("import", "T"), ("protect", "new")]))

    def test_filtered_folder_mail_already_here_is_skipped(self):
        same = {"e1": {"mailboxIds": {"X": True}}}
        self.assertEqual(self.run_case("INBOX", same, same), ("skip", []))

    def test_other_folder_is_imported_and_protected(self):
        self.assertEqual(self.run_case("Archive"), ("jmap", [("import", "T"), ("protect", "new")]))

    def test_retry_is_not_imported_again(self):
        same = {"e1": {"mailboxIds": {"T": True}}}
        self.assertEqual(self.run_case("Archive", same, same), ("retry", [("protect", "e1")]))

    def test_label_adds_a_folder_to_a_human_placed_mail(self):
        same = {"e1": {"mailboxIds": {"B": True}}}
        self.assertEqual(self.run_case("Archive", same, same, protected={"e1"}),
                         ("add-folder", [("set", "e1", {"mailboxIds/T": True}), ("protect", "e1")]))

    def test_provider_move_moves_a_filter_placed_mail(self):
        same = {"e1": {"mailboxIds": {"INBOX": True}}}
        self.assertEqual(self.run_case("Archive", same, same),
                         ("move", [("set", "e1", {"mailboxIds": {"T": True}}), ("protect", "e1")]))

    def test_provider_sent_copy_is_skipped(self):
        same = {"e1": {"mailboxIds": {"T": True}}}       # same Message-ID, other bytes
        self.assertEqual(self.run_case("Sent", same, {}, target_role="sent"), ("skip-sent", []))

    def test_mail_to_oneself_arrives_despite_the_sent_copy(self):
        # Sent from webmail to one's own address: Roundcube's Sent copy is
        # identical, but the mail has not arrived yet (found in daily use, 2026-10-09).
        sent = {"e1": {"mailboxIds": {"S": True}}}
        self.assertEqual(self.run_case("INBOX", sent, sent, roles={"S": "sent"}), ("smtp", [("smtp", False)]))
        drafts_and_sent = {"e1": {"mailboxIds": {"S": True, "D": True}}}
        self.assertEqual(self.run_case("INBOX", drafts_and_sent, drafts_and_sent,
                                       roles={"S": "sent", "D": "drafts"}), ("smtp", [("smtp", False)]))

    def test_mail_to_oneself_in_another_folder_leaves_sent_alone(self):
        sent = {"e1": {"mailboxIds": {"S": True}}}
        self.assertEqual(self.run_case("Archive", sent, sent, roles={"S": "sent"}),
                         ("jmap", [("import", "T"), ("protect", "new")]))

    def test_gmail_label_adds_a_folder_never_moves(self):
        # Gmail: a filter-placed INBOX mail seen under a label keeps INBOX.
        inbox = {"e1": {"mailboxIds": {"I": True}}}
        self.assertEqual(self.run_case("Work", inbox, inbox, roles={"I": "inbox"}, labels=True),
                         ("add-folder", [("set", "e1", {"mailboxIds/T": True}), ("protect", "e1")]))

    def test_sent_copy_from_another_client_keeps_the_inbox_copy(self):
        # Sent to oneself from a phone: INBOX copy delivered, then the
        # provider's Sent copy; no Sent copy here yet. INBOX must stay.
        inbox = {"e1": {"mailboxIds": {"I": True}}}
        self.assertEqual(self.run_case("Sent", inbox, inbox, target_role="sent", roles={"I": "inbox"}),
                         ("add-folder", [("set", "e1", {"mailboxIds/T": True}), ("protect", "e1")]))

    def test_mail_to_oneself_fetched_twice_is_skipped(self):
        both = {"e1": {"mailboxIds": {"S": True, "I": True}}}
        self.assertEqual(self.run_case("INBOX", both, both, roles={"S": "sent", "I": "inbox"}), ("skip", []))

    def test_listed_junk_matches_the_providers_spam_folder_by_role(self):
        self.assertEqual(self.run_case("[Gmail]/Spam", role="junk", sieve=("inbox", "junk")),
                         ("smtp-junk", [("smtp", True)]))

    def test_not_spam_at_the_provider_moves_it_here_too(self):
        junk = {"e1": {"mailboxIds": {"J": True}}}
        method, log = self.run_case("INBOX", junk, junk, roles={"J": "junk"})
        self.assertEqual(method, "not-spam")
        self.assertEqual(log, [("set", "e1", {"mailboxIds": {"T": True}, "keywords/$notjunk": True,
                                               "keywords/$junk": None})])

    def test_gmail_mark_as_spam_moves_even_with_labels(self):
        # Found live 2026-10-09: marked as spam in Gmail, the INBOX copy
        # here got Junk added and stayed in INBOX. Spam is a place.
        inbox = {"e1": {"mailboxIds": {"I": True}}}
        self.assertEqual(self.run_case("[Gmail]/Spam", inbox, inbox, role="junk", target_role="junk",
                                       roles={"I": "inbox"}, labels=True),
                         ("move", [("set", "e1", {"mailboxIds": {"T": True}, "keywords/$junk": True,
                                                  "keywords/$notjunk": None}), ("protect", "e1")]))

    def test_deleted_at_the_provider_moves_to_trash_also_when_placed_by_a_human(self):
        placed = {"e1": {"mailboxIds": {"B": True, "W": True}}}
        self.assertEqual(self.run_case("[Gmail]/Trash", placed, placed, protected={"e1"}, target_role="trash",
                                       roles={"B": None, "W": None}, labels=True),
                         ("move", [("set", "e1", {"mailboxIds": {"T": True}}), ("protect", "e1")]))

    def test_not_spam_into_a_label_leaves_junk(self):
        junk = {"e1": {"mailboxIds": {"J": True}}}
        self.assertEqual(self.run_case("Work", junk, junk, roles={"J": "junk"}, labels=True),
                         ("move", [("set", "e1", {"mailboxIds": {"T": True}, "keywords/$notjunk": True,
                                                  "keywords/$junk": None}), ("protect", "e1")]))

    def test_restored_from_trash_into_the_inbox(self):
        trash = {"e1": {"mailboxIds": {"R": True}}}
        self.assertEqual(self.run_case("INBOX", trash, trash, roles={"R": "trash"}, labels=True),
                         ("move", [("set", "e1", {"mailboxIds": {"T": True}})]))

    def test_label_on_a_mail_in_inbox_and_junk_is_still_a_label(self):
        # Only a copy that is nowhere but in spam/trash leaves it.
        both = {"e1": {"mailboxIds": {"I": True, "J": True}}}
        self.assertEqual(self.run_case("Work", both, both, roles={"I": "inbox", "J": "junk"}, labels=True),
                         ("add-folder", [("set", "e1", {"mailboxIds/T": True}), ("protect", "e1")]))

    def test_marked_as_spam_later_when_junk_goes_through_the_filter(self):
        # inbound_sieve.folders [INBOX, Junk]: a mail fetched before, moved
        # into the provider's spam folder afterwards, moves into Junk here.
        kept = {"e1": {"mailboxIds": {"P": True}}}
        self.assertEqual(self.run_case("INBOX.Spam", kept, kept, role="junk", target_role="junk",
                                       sieve=("inbox", "junk"), roles={"P": None}),
                         ("move", [("set", "e1", {"mailboxIds": {"T": True}, "keywords/$junk": True,
                                                  "keywords/$notjunk": None}), ("protect", "e1")]))
        here = {"e1": {"mailboxIds": {"T": True}}}       # already in Junk: nothing to do
        self.assertEqual(self.run_case("INBOX.Spam", here, here, role="junk", target_role="junk",
                                       sieve=("inbox", "junk")), ("retry", [("protect", "e1")]))

    def test_stale_folder_list_is_reloaded_once(self):
        # A folder made in webmail meanwhile: the first import fails, the
        # folder list is read again, the second attempt succeeds.
        calls, forgotten = [], []
        saved = (bridge.JMAP.import_new, bridge.JMAP.forget_mailboxes)
        def flaky(raw, target, session, user):
            calls.append(target)
            if len(calls) == 1:
                raise RuntimeError("Mailbox creation failed")
            return "new"
        bridge.JMAP.forget_mailboxes = lambda user: forgotten.append(user)
        try:
            jsaved = bridge.JMAP.import_new
            bridge.JMAP.import_new = flaky
            method, _ = self.run_case("Archive", keep_import=True)
        finally:
            bridge.JMAP.import_new, bridge.JMAP.forget_mailboxes = saved
        self.assertEqual((method, len(calls), forgotten), ("jmap", 2, ["a@x.test"]))

    def test_same_message_id_other_content_is_its_own_mail(self):
        same = {"e1": {"mailboxIds": {"B": True}}}
        self.assertEqual(self.run_case("Archive", same, {}), ("jmap", [("import", "T"), ("protect", "new")]))


if __name__ == "__main__":
    unittest.main()
