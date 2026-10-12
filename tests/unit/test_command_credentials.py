import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CommandCredentials(unittest.TestCase):
    def test_resieve_by_hand_runs_inside_the_stack(self):
        # tools/resieve hands only the account and options to resieve-watch,
        # which reads the login itself: no password on the host.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "resieve"
            wrapper.write_text((ROOT / "tools/resieve").read_text())
            (root / "layout.sh").write_text('mailstack_compose() { python3 "$TEST_ROOT/capture.py" "$@"; }\n')
            (root / "capture.py").write_text(
                'import json,os,sys\n'
                'json.dump(sys.argv[1:], open(os.environ["TEST_ROOT"]+"/capture.json","w"))\n')
            result = subprocess.run(["bash", str(wrapper), "person", "--apply"], capture_output=True,
                                    env=dict(os.environ, TEST_ROOT=str(root)))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root / "capture.json").read_text()),
                             ["exec", "-T", "resieve-watch", "python3", "/usr/local/bin/resieve-watch",
                              "resieve", "person", "--apply"])

    def test_folder_scan_credentials_in_a_file_and_escaped(self):
        # generate-config writes <account>.curl; the scan hands curl only
        # that file's name, never the login.
        import importlib.util, sys
        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location("generate_config", ROOT / "tools" / "generate-config.py")
        generate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generate)
        token = 'synthetic-' + 'private:"\\value'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            account = {"inbound": {"active": True, "host": "provider.test", "port": 993,
                                   "username": "person", "password": token}}
            generate.generate_getmail("person", account, root, {"version": 1})
            config = root / "getmail" / "person.conf"
            curl_file = (root / "getmail" / "person.curl").read_text()
            escaped = ("person:" + token).replace("\\", "\\\\").replace('"', '\\"')
            self.assertEqual(curl_file, 'url = "imaps://provider.test:993/"\nuser = "' + escaped + '"\n')
            self.assertEqual((root / "getmail" / "person.curl").stat().st_mode & 0o777, 0o600)
            curl = root / "curl"
            curl.write_text(
                '#!/usr/bin/env python3\nimport json,os,sys\n'
                'json.dump({"args":sys.argv[1:]},open(os.environ["TEST_ROOT"]+"/capture.json","w"))\n'
                'print(\'* LIST () "/" "INBOX"\')\n')
            curl.chmod(0o700)
            (root / "person").mkdir()
            source = (ROOT / "getmail/entrypoint.sh").read_text().split("trap shutdown TERM INT")[0]
            runner = root / "scan.sh"
            runner.write_text(source + f'\nSTATE_ROOT="$TEST_ROOT"\nscan_folders person "{config}"\n')
            result = subprocess.run(["bash", str(runner)], capture_output=True,
                                    env=dict(os.environ, TEST_ROOT=str(root), SCAN_INTERVAL="300",
                                             PATH=str(root) + ":" + os.environ["PATH"]))
            # First list of this account: a baseline, reported as changed (10)
            # so that it is applied and getmail started.
            self.assertEqual(result.returncode, 10, result.stderr)
            captured = json.loads((root / "capture.json").read_text())
            self.assertTrue(token not in repr(captured["args"]))
            self.assertTrue(token.encode() not in result.stdout + result.stderr)
            self.assertEqual(captured["args"][:2], ["--config", str(root / "getmail" / "person.curl")])
