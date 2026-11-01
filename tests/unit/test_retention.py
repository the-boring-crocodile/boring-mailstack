"""Regression coverage for explicit, global mail-retention provisioning."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class RetentionProvisioning(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "retention_provision", ROOT / "tools" / "stalwart-provision.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def reconcile(self, actual, apply):
        module = self.module
        def current(name):
            if name == "DataRetention":
                return actual
            return next(dict(wanted) for obj, _, wanted in module.SINGLETONS if obj == name)
        # Exercise the real SINGLETONS and update_object serialization.
        with patch.object(module, "get_json", side_effect=current), patch.object(
            module, "NAMED", []
        ), patch.object(module, "cli") as cli, contextlib.redirect_stdout(io.StringIO()):
            module.reconcile_settings(apply)
        return cli

    def test_upgrade_disables_default_and_preserves_other_maintenance(self):
        cli = self.reconcile({
            "expungeTrashAfter": 2592000000,
            "expungeSubmissionsAfter": 259200000,
            "blobCleanupSchedule": {"@type": "Daily", "hour": 4, "minute": 0},
        }, True)
        cli.assert_called_once()
        args, kwargs = cli.call_args
        self.assertEqual(args, ("update", "DataRetention", "--stdin"))
        self.assertEqual(json.loads(kwargs["stdin"]), {"expungeTrashAfter": None})

    def test_missing_field_is_explicitly_disabled(self):
        cli = self.reconcile({}, True)
        cli.assert_called_once()
        self.assertEqual(json.loads(cli.call_args.kwargs["stdin"]), {"expungeTrashAfter": None})

    def test_already_disabled_is_idempotent(self):
        self.reconcile({"expungeTrashAfter": None}, True).assert_not_called()

    def test_preview_does_not_change_retention(self):
        self.reconcile({"expungeTrashAfter": 2592000000}, False).assert_not_called()


if __name__ == "__main__":
    unittest.main()
