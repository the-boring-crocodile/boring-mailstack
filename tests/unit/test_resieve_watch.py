"""Unit tests for resieve/watch.py (no Stalwart, no resieve binary)."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("watch", ROOT / "resieve" / "watch.py")
watch = importlib.util.module_from_spec(_spec)
sys.modules["watch"] = watch
_spec.loader.exec_module(watch)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Fake:
    def __init__(self, scripts, run_ok=True):
        self.scripts = scripts          # name -> digest (None: no active script)
        self.runs = []
        self.run_ok = run_ok

    def accounts(self):
        return [{"id": n} for n in self.scripts]

    def check(self, account):
        value = self.scripts[account["id"]]
        if isinstance(value, Exception):
            raise value
        return value

    def run(self, account, resort_ids=None):
        self.runs.append((account["id"], sorted(resort_ids)) if resort_ids else account["id"])
        return self.run_ok


def watcher(fake, state=None):
    d = tempfile.mkdtemp()
    path = Path(d) / "applied.json"
    if state is not None:
        path.write_text(json.dumps(state))
    clock = Clock()
    fake.notices = []
    w = watch.Watcher(check=fake.check, run=fake.run, accounts=fake.accounts,
                      state_path=path, clock=clock, notify=lambda a: fake.notices.append(a["id"]))
    return w, clock, path


class Reconcile(unittest.TestCase):
    def test_first_start_records_without_running(self):
        fake = Fake({"croc": "a", "tim": "b"})
        w, _, path = watcher(fake)
        self.assertEqual(w.reconcile(), [])
        self.assertEqual(fake.runs, [])
        self.assertEqual(json.loads(path.read_text()), {"croc": "a", "tim": "b"})

    def test_changed_script_runs_that_account_only(self):
        fake = Fake({"croc": "a2", "tim": "b"})
        w, _, path = watcher(fake, {"croc": "a", "tim": "b"})
        self.assertEqual(w.reconcile(), ["croc"])
        self.assertEqual(json.loads(path.read_text())["croc"], "a2")
        self.assertEqual(w.reconcile(), [], "no second run for the same script")

    def test_failed_run_is_retried_next_time(self):
        fake = Fake({"croc": "a2"}, run_ok=False)
        w, _, path = watcher(fake, {"croc": "a"})
        self.assertEqual(w.reconcile(), [])
        self.assertEqual(json.loads(path.read_text())["croc"], "a")
        fake.run_ok = True
        self.assertEqual(w.reconcile(), ["croc"])

    def test_failing_version_is_given_up_after_max_failures(self):
        fake = Fake({"croc": "b"}, run_ok=False)
        w, _, _ = watcher(fake, {"croc": "a"})
        for _ in range(watch.MAX_FAILURES + 2):
            w.reconcile()
        self.assertEqual(fake.runs, ["croc"] * watch.MAX_FAILURES)
        fake.scripts["croc"] = "c"          # the next filter change runs again
        w.reconcile()
        self.assertEqual(len(fake.runs), watch.MAX_FAILURES + 1)

    def test_activating_a_script_runs(self):
        fake = Fake({"croc": "a"})
        w, _, _ = watcher(fake, {"croc": None})
        self.assertEqual(w.reconcile(), ["croc"])

    def test_deactivating_runs_nothing(self):
        fake = Fake({"croc": None})
        w, _, path = watcher(fake, {"croc": "a"})
        self.assertEqual(w.reconcile(), [])
        self.assertIsNone(json.loads(path.read_text())["croc"])

    def test_new_account_is_recorded_not_run(self):
        fake = Fake({"croc": "a", "otter": "o"})
        w, _, _ = watcher(fake, {"croc": "a"})
        self.assertEqual(w.reconcile(), [])
        self.assertEqual(fake.runs, [])

    def test_unreachable_account_is_skipped(self):
        fake = Fake({"croc": OSError("down"), "tim": "b2"})
        w, _, _ = watcher(fake, {"croc": "a", "tim": "b"})
        self.assertEqual(w.reconcile(), ["tim"])


class Debounce(unittest.TestCase):
    def test_waits_for_quiet(self):
        fake = Fake({"croc": "a"})
        w, clock, _ = watcher(fake, {"croc": "a"})
        self.assertFalse(w.due())
        w.event()
        clock.now += watch.QUIET_SECONDS - 1
        self.assertFalse(w.due())
        w.event()                               # another save: wait again
        clock.now += watch.QUIET_SECONDS - 1
        self.assertFalse(w.due())
        clock.now += 1
        self.assertTrue(w.due())
        w.reconcile()
        self.assertFalse(w.due())


class Accounts(unittest.TestCase):
    def test_opt_out(self):
        d = tempfile.mkdtemp()
        path = Path(d) / "accounts.json"
        path.write_text(json.dumps([{"id": "a", "resieve_enabled": True},
                                    {"id": "b", "resieve_enabled": False},
                                    {"id": "c", "resieve_enabled": True}]))
        saved, watch.ACCOUNTS = watch.ACCOUNTS, path
        try:
            self.assertEqual([a["id"] for a in watch.load_accounts()], ["a", "c"])
        finally:
            watch.ACCOUNTS = saved


class Resort(unittest.TestCase):
    def test_moves_batched_until_quiet(self):
        fake = Fake({"croc": "a"})
        w, clock, _ = watcher(fake)
        w.add_resort("croc", ["e1", "e2"])
        clock.now += watch.QUIET_SECONDS - 1
        w.add_resort("croc", ["e3"])
        self.assertEqual(w.resort_due(), [])            # still moving
        clock.now += watch.QUIET_SECONDS
        self.assertEqual(w.resort_due(), ["croc"])
        self.assertEqual(fake.runs, [("croc", ["e1", "e2", "e3"])])
        self.assertEqual(w.resort_due(), [])            # done

    def test_not_enabled_account_left_alone(self):
        fake = Fake({"croc": "a"})
        w, clock, _ = watcher(fake)
        w.add_resort("tim", ["e1"])
        clock.now += watch.QUIET_SECONDS
        self.assertEqual(w.resort_due(), [])
        self.assertEqual(fake.runs, [])


    def test_pending_resorts_survive_a_restart(self):
        fake = Fake({"croc": "a"})
        w, clock, path = watcher(fake)
        w.add_resort("croc", ["e1", "e2"])
        again = watch.Watcher(check=fake.check, run=fake.run, accounts=fake.accounts,
                              state_path=path, clock=clock, notify=lambda a: None)
        clock.now += watch.QUIET_SECONDS
        self.assertEqual(again.resort_due(), ["croc"])
        self.assertEqual(fake.runs, [("croc", ["e1", "e2"])])
        self.assertEqual(json.loads(path.with_name("resort.json").read_text()), {})

    def test_a_run_that_cannot_start_does_not_stop_the_watcher(self):
        fake = Fake({"croc": "a"})
        def broken(account, resort_ids=None):
            raise OSError(7, "Argument list too long")
        w, clock, _ = watcher(fake)
        w.run = broken
        w.add_resort("croc", ["e1"])
        clock.now += watch.QUIET_SECONDS
        self.assertEqual(w.resort_due(), [])            # logged, not raised


class RunResieve(unittest.TestCase):
    def test_many_resort_ids_go_in_a_file(self):
        seen = {}
        def fake_run(cmd, env, **kw):
            seen["env"] = env
            seen["ids"] = Path(env["RESIEVE_RESORT_IDS_FILE"]).read_text().split()
            class Done:
                returncode, stdout, stderr = 0, "", ""
            return Done()
        saved = watch.subprocess.run
        watch.subprocess.run = fake_run
        try:
            ids = [f"e{i:07d}" for i in range(20000)]      # ~180 KB: too much for one variable
            self.assertTrue(watch.run_resieve({"id": "croc", "login": "c@x.test", "password": "p"}, ids))
        finally:
            watch.subprocess.run = saved
        self.assertEqual(len(seen["ids"]), 20000)
        self.assertNotIn("RESIEVE_RESORT_IDS", seen["env"])
        self.assertFalse(Path(seen["env"]["RESIEVE_RESORT_IDS_FILE"]).exists())   # removed afterwards


class ByHand(unittest.TestCase):
    def test_account_settings_and_options(self):
        d = tempfile.mkdtemp()
        accounts = Path(d) / "accounts.json"
        accounts.write_text(json.dumps([{"id": "croc", "login": "croc@x.test", "password": "p",
                                          "resieve_enabled": False, "resieve_protected_folders": ["Sent"]}]))
        seen = {}
        def fake_execve(path, argv, env):
            seen.update(env)
            raise SystemExit(0)
        saved = watch.ACCOUNTS, watch.os.execve
        watch.ACCOUNTS, watch.os.execve = accounts, fake_execve
        try:
            with self.assertRaises(SystemExit):
                watch.resieve_by_hand(["croc", "--apply", "--limit", "5", "--mailbox", "INBOX"])
            with self.assertRaises(SystemExit) as unknown:
                watch.resieve_by_hand(["otter"])
        finally:
            watch.ACCOUNTS, watch.os.execve = saved
        self.assertEqual((seen["RESIEVE_USERNAME"], seen["RESIEVE_ACCOUNT"], seen["RESIEVE_APPLY"]),
                         ("croc@x.test", "croc", "1"))     # also with resieve.enabled false
        self.assertEqual((seen["RESIEVE_LIMIT"], seen["RESIEVE_MAILBOX"], seen["RESIEVE_PROTECTED_FOLDERS"]),
                         ("5", "INBOX", "Sent"))
        self.assertIn("unknown account", str(unknown.exception.code))


class GaveUp(unittest.TestCase):
    def test_notice_after_the_last_failure(self):
        fake = Fake({"croc": "a"}, run_ok=False)
        w, _, _ = watcher(fake, {"croc": "old"})
        for _ in range(watch.MAX_FAILURES + 1):
            w.reconcile()
        self.assertEqual(fake.notices, ["croc"])        # once


if __name__ == "__main__":
    unittest.main()
