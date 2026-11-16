"""Acceptance tests for monorepo ownership, environments, and honest verdicts."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import Repository
from regression_guard.engine import inspect
from regression_guard.process import ProcessResult

ROOT = Path(__file__).resolve().parents[1]


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.addCleanup(self.repo.close)

    def check(self, **options):
        return inspect(self.repo.path, timeout=10, execute=True, **options)

    def test_nested_python_runs_from_its_own_project(self):
        test = "apps/ui/tests/test_status.py"
        self.repo.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths=["tests"]\n')
        self.repo.write("tests/test_status.py", "def test_unrelated(): assert False\n")
        self.repo.write("apps/ui/pytest.ini", "[pytest]\ntestpaths=tests\n")
        self.repo.write("apps/ui/src/status.py", "READY = True\n")
        self.repo.write(test, "from src.status import READY\ndef test_ready(): assert READY\n")
        self.repo.commit()
        self.repo.write("apps/ui/src/status.py", "READY = not False\n")
        report = self.check()
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["executed"], [test])
        package = next(r for r in report["runners"] if r["directory"] == "apps/ui")
        self.assertEqual(package["commands"][0][-1], "./tests/test_status.py")

    def test_collection_and_missing_dependency_are_not_failed_cases(self):
        test = "test_runtime.py"
        for code, reason in (
            ("import rg_missing_dependency_120\n", "environment_unavailable"),
            ("def broken(\n", "collection_error"),
            ("def test_value(): assert False\n", "test_failure"),
        ):
            with self.subTest(reason=reason):
                self.repo.write(test, code + "\ndef test_smoke(): assert True\n")
                report = self.check()
                self.assertEqual(report["runners"][0]["outcomes"][test], reason, report)
                self.assertEqual(report["status"], "FAIL" if reason == "test_failure" else "UNKNOWN")
                self.assertEqual(report["case_counts"]["failed"], int(reason == "test_failure"))
                self.assertEqual(report["risk"], "low")

    def test_process_launch_error_has_its_own_reason(self):
        self.repo.write("test_probe.py", "def test_ready(): assert True\n")
        with patch("regression_guard.execution.invoke", return_value=ProcessResult(error="cannot spawn")):
            report = self.check()
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertIn("infrastructure_error", report["reasons"])
        self.assertEqual(report["failed"], [])

    def test_no_selection_and_budget_exhaustion_have_distinct_reasons(self):
        self.repo.write("test_probe.py", "def test_ready(): assert True\n")
        self.repo.commit()
        self.repo.write("data.json", "{}\n")
        unmapped = self.check()
        self.assertEqual(unmapped["status"], "UNKNOWN")
        self.assertIn("no_tests_selected", unmapped["reasons"])
        self.assertIn("insufficient_evidence", unmapped["reasons"])
        self.assertEqual(unmapped["risk"], "low")
        self.repo.write("test_probe.py", "def test_ready(): assert 1 == 1\n")
        with patch("regression_guard.execution.invoke", return_value=ProcessResult(timed_out=True)):
            timed = self.check()
        self.assertEqual(timed["status"], "INCOMPLETE")
        self.assertIn("budget_exhausted", timed["reasons"])
        self.assertEqual(timed["pending"], ["test_probe.py"])

    def test_remote_profiles_do_not_launch_any_runner(self):
        self.repo.write("test_probe.py", "def test_ready(): assert True\n")
        for kind in ("wsl", "docker"):
            with self.subTest(kind=kind):
                self.repo.write(".regression-guard.toml", f'[environments."."]\nkind="{kind}"\nprofile="ci"\n')
                with patch("regression_guard.execution.invoke", side_effect=AssertionError("launched")):
                    report = self.check()
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertIn("environment_unavailable", report["reasons"])
                self.assertEqual(report["runners"][0]["environment"]["kind"], kind)
                self.assertEqual(report["executed"], [])

    def test_existing_virtualenv_is_used_for_unittest(self):
        self.repo.write("pyproject.toml", '[project]\nname="demo"\nversion="1.0.0"\n')
        self.repo.write("test_probe.py", "import sys, unittest\nclass Probe(unittest.TestCase):\n"
                        "    def test_env(self): self.assertNotEqual(sys.prefix, sys.base_prefix)\n")
        self.repo.commit()
        subprocess.run([sys.executable, "-B", "-m", "venv", "--without-pip", str(self.repo.path / ".venv")],
                       timeout=12, check=True, capture_output=True)
        self.repo.write("test_probe.py", (self.repo.path / "test_probe.py").read_text() + "\n# changed\n")
        report = self.check()
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["runners"][0]["environment"]["source"], "venv")

    def test_mapping_selects_unchanged_test_in_cli_and_hooks(self):
        self.repo.write(".regression-guard.toml", '[[mappings]]\nchanges=["data/CURRENT", "data/*.json"]\n'
                        'tests=["tests/test_data.py"]\n')
        self.repo.write("data/CURRENT", "a.json\n")
        self.repo.write("data/a.json", '{"valid":true}\n')
        self.repo.write("data/b.json", '{"valid":true}\n')
        self.repo.write("tests/test_data.py", "import json\nfrom pathlib import Path\n"
                        "def test_manifest():\n    p = Path('data')\n"
                        "    assert json.loads((p / (p / 'CURRENT').read_text().strip()).read_text())['valid']\n")
        self.repo.commit()
        env = {**os.environ, "TEMP": str(self.repo.path / ".git"), "TMP": str(self.repo.path / ".git"),
               "TMPDIR": str(self.repo.path / ".git"), "REGRESSION_GUARD_TIMEOUT": "8"}
        for agent in ("codex", "claude"):
            with self.subTest(agent=agent):
                payload = json.dumps({"session_id": "mapping-fixture", "cwd": str(self.repo.path)})
                command = [sys.executable, "-B", str(ROOT / "integrations/hooks/auto_check.py"), "--agent", agent]
                self.repo.write("data/CURRENT", "a.json\n")
                subprocess.run([*command, "--phase", "start"], input=payload, text=True,
                               env=env, timeout=10, capture_output=True, check=True)
                self.repo.write("data/CURRENT", "b.json\n")
                outcome = subprocess.run([*command, "--phase", "stop"], input=payload, text=True,
                                         env=env, timeout=15, capture_output=True, check=True)
                self.assertIn("Regression Guard: PASS", outcome.stdout)
                self.assertIn("mapping 1: data/CURRENT", outcome.stdout)
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/run.py"), "check",
                                 "--repo", str(self.repo.path), "--timeout", "8", "--compact"],
                                timeout=12, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("mapping 1: data/CURRENT", result.stdout)
        self.repo.write("data/CURRENT", "a.json\n")
        self.repo.write("data/a.json", '{"valid":true,"revision":2}\n')
        manifest = self.check()
        self.assertEqual(manifest["executed"], ["tests/test_data.py"])
        self.assertIn("mapping 1: data/a.json", str(manifest["runners"][0]["selection_reasons"]))

    @unittest.skipUnless(shutil.which("node"), "Node is required")
    def test_nested_node_package_and_overlapping_scripts_execute_one_case(self):
        self.repo.write("package.json", '{"workspaces":["packages/*"],"scripts":{"test":"node --test"}}')
        self.repo.write("packages/worker/package.json", '{"scripts":{"test":"node --test",'
                        '"test:unit":"node --test check.test.mjs"}}')
        test = "packages/worker/check.test.mjs"
        self.repo.write(test, "import {test} from 'node:test'; test('example',()=>{});\n")
        self.repo.commit()
        self.repo.write(test, "import {test} from 'node:test'; test('changed',()=>{});\n")
        report = self.check()
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["executed"], [test])
        self.assertEqual(report["case_counts"]["passed"], 1)
        self.assertEqual(sum(len(r["executed"]) for r in report["runners"]), 1)
        self.assertEqual(report["runners"][0]["discovered"], [])

    @unittest.skipUnless(shutil.which("node"), "Node is required")
    def test_hoisted_framework_contracts_find_nested_typescript(self):
        for runner, binary in (("vitest", "vitest/vitest.mjs"), ("jest", "jest/bin/jest.js")):
            with self.subTest(runner=runner):
                test = "packages/ui/check.test.ts"
                self.repo.write("package.json", '{"workspaces":["packages/*"]}')
                self.repo.write("packages/ui/package.json", json.dumps({"scripts": {"test": runner}}))
                self.repo.write(test, "const value: number = 1;\n")
                self.repo.write("node_modules/" + binary,
                                "const listing = process.argv.includes('list') || process.argv.includes('--listTests');\n"
                                "console.log(JSON.stringify(listing ? ['check.test.ts'] : "
                                "{numTotalTests:1,numPassedTests:1,numFailedTests:0}));\n")
                self.repo.commit()
                self.repo.write(test, "const value: number = 2;\n")
                report = self.check()
                self.assertEqual(report["status"], "PASS", report)
                self.assertEqual(report["executed"], [test], report)
                self.assertEqual(report["case_counts"]["passed"], 1)

    @unittest.skipUnless(shutil.which("node"), "Node is required")
    def test_node_loader_error_does_not_count_file_wrapper_as_test(self):
        self.repo.write("probe.test.mjs", "import './missing.mjs';\n")
        self.repo.write("package.json", '{"scripts":{"test":"node --test"}}')
        report = self.check()
        self.assertEqual(report["status"], "UNKNOWN", report)
        self.assertIn("environment_unavailable", report["reasons"])
        self.assertEqual(report["case_counts"]["failed"], 0)
