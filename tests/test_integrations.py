"""Exercise the same CLI through each lifecycle payload adapter."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import Repository, fixture

HOOK = Path(__file__).resolve().parents[1] / "integrations/hooks/auto_check.py"


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.source, self.test = fixture(self.repo, "node:test")
        self.repo.commit()

    def tearDown(self):
        self.repo.close()

    def hook(self, phase, agent, **fields):
        payload = ({"conversationId": self.repo.path.name,
                    "workspacePaths": [str(self.repo.path)], "invocationNum": 1}
                   if agent == "antigravity" else
                   {"session_id": self.repo.path.name, "cwd": str(self.repo.path)})
        payload.update(fields)
        p = subprocess.run([sys.executable, "-B", str(HOOK), "--agent", agent, "--phase", phase],
                           input=json.dumps(payload), text=True, capture_output=True,
                           timeout=20, check=True)
        return json.loads(p.stdout)

    def message(self, output, agent):
        return (output["hookSpecificOutput"]["additionalContext"] if agent == "claude"
                else output["report"] if agent == "generic" else output["reason"])

    def test_all_payload_adapters_delegate_to_shared_node_backend_once(self):
        for agent in ("codex", "claude", "antigravity", "generic"):
            with self.subTest(agent=agent):
                self.repo.write(self.source, "export function value(){return 1}\n")
                self.hook("start", agent)
                self.repo.write(self.source, "export function value(){return 1+0}\n")
                if agent == "antigravity":
                    self.assertEqual(self.hook("start", agent, invocationNum=2), {})
                result = self.hook("stop", agent)
                message = self.message(result, agent)
                self.assertIn("Regression Guard: PASS", message)
                self.assertIn("runner: node:test@.", message)
                self.assertIn("executed: 1", message)
                self.assertEqual(self.hook("stop", agent), {})

    def test_committed_changes_use_baseline_commit(self):
        self.hook("start", "codex")
        self.repo.write(self.source, "export function value(){return 1+0}\n")
        self.repo.commit()
        self.assertIn("Regression Guard: PASS", self.message(self.hook("stop", "codex"), "codex"))

    def test_preexisting_node_changes_and_documentation_do_not_trigger(self):
        self.repo.write(self.source, "export function value(){return 1+0}\n")
        self.hook("start", "codex")
        self.repo.write("README.md", "documentation\n")
        self.assertEqual(self.hook("stop", "codex"), {})

    def test_missing_baseline_and_unsupported_multi_workspace_are_silent(self):
        self.assertEqual(self.hook("stop", "generic"), {})
        self.assertEqual(self.hook("start", "antigravity", workspacePaths=["a", "b"]), {})

    def test_disable_switch_and_invalid_input_do_not_run_tests(self):
        for payload in ("invalid", "[]", "null", "42"):
            process = subprocess.run([sys.executable, "-B", str(HOOK), "--agent", "codex", "--phase", "start"],
                                     input=payload, capture_output=True, text=True, timeout=10, check=True)
            self.assertEqual(json.loads(process.stdout), {})
        env = {**os.environ, "REGRESSION_GUARD_DISABLE": "1"}
        process = subprocess.run([sys.executable, "-B", str(HOOK), "--agent", "generic", "--phase", "stop"],
                                 input=json.dumps({"session_id": "disabled", "cwd": str(self.repo.path)}),
                                 capture_output=True, text=True, timeout=10, env=env, check=True)
        self.assertEqual(json.loads(process.stdout), {})

    def test_cli_analysis_and_json_use_same_engine_without_tests(self):
        run = HOOK.parents[2] / "scripts/run.py"
        self.repo.write(self.source, "export function value(){return 1+0}\n")
        report_path = self.repo.path / "result.json"
        process = subprocess.run([sys.executable, "-B", str(run), "analyze", "--repo", str(self.repo.path),
                                  "--json", str(report_path)], capture_output=True, text=True, timeout=10)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(process.returncode, 2)
        self.assertEqual(report["selected"], [self.test])
        self.assertEqual(report["executed"], [])


if __name__ == "__main__":
    unittest.main()
