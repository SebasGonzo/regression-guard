import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "integrations" / "hooks" / "auto_check.py"


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rg-hook-")
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"], check=True)
        (self.repo / "calc.py").write_text("def value(): return 1\n")
        (self.repo / "test_calc.py").write_text("from calc import value\ndef test_value(): assert value() == 1\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        self.session = self.repo.name

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, phase, agent="codex", **fields):
        payload = {"session_id": self.session, "cwd": str(self.repo),
                   "hook_event_name": "UserPromptSubmit" if phase == "start" else "Stop", **fields}
        p = subprocess.run([sys.executable, str(HOOK), "--agent", agent, "--phase", phase],
                           input=json.dumps(payload), text=True, capture_output=True, check=True)
        return json.loads(p.stdout)

    def test_only_changed_code_runs_and_only_once(self):
        self.hook("start")
        self.assertEqual(self.hook("stop"), {})
        (self.repo / "README.md").write_text("documentation\n")
        self.assertEqual(self.hook("stop"), {})
        (self.repo / "calc.py").write_text("def value(): return 1 + 0\n")
        result = self.hook("stop")
        self.assertIn("Regression Guard: PASS", result["reason"])
        self.assertEqual(self.hook("stop"), {})
        self.assertEqual(self.hook("stop", stop_hook_active=True), {})

    def test_preexisting_dirty_code_does_not_run(self):
        (self.repo / "calc.py").write_text("def value(): return 1 + 0\n")
        self.hook("start", agent="claude")
        self.assertEqual(self.hook("stop", agent="claude"), {})
        (self.repo / "calc.py").write_text("def value(): return 0\n")
        result = self.hook("stop", agent="claude")
        self.assertIn("Regression Guard: FAIL", result["hookSpecificOutput"]["additionalContext"])

    def test_no_tests_is_unknown(self):
        (self.repo / "test_calc.py").unlink()
        self.hook("start")
        (self.repo / "calc.py").write_text("def value(): return 2\n")
        result = self.hook("stop")
        self.assertIn("Regression Guard: UNKNOWN", result["reason"])
