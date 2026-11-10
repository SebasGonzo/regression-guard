"""Opt-in smoke tests with real project-local npm dependencies; never installs packages."""
import json
import os
import subprocess
import unittest
from pathlib import Path

from regression_guard.engine import inspect

ROOT = os.environ.get("REGRESSION_GUARD_REAL_JS_ROOT", "")


@unittest.skipUnless(ROOT, "Set REGRESSION_GUARD_REAL_JS_ROOT to the dedicated temporary dependency fixture.")
class RealJavaScriptRunners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(ROOT).resolve()
        if not cls.repo.name.startswith("regression-guard-real-runners-"):
            raise RuntimeError("Expected a dedicated Regression Guard fixture, not a consumer repository.")
        if not all((cls.repo / "node_modules" / p).is_file()
                   for p in ("vitest/vitest.mjs", "jest/bin/jest.js")):
            raise RuntimeError("Install the explicitly documented fixture dependencies first.")
        cls.git("init", "-q")
        cls.git("config", "user.name", "Regression Guard Test")
        cls.git("config", "user.email", "test@example.invalid")
        cls.write(".gitignore", "node_modules/\n")

    @classmethod
    def git(cls, *args):
        subprocess.run(["git", "-C", str(cls.repo), *args], check=True, capture_output=True, timeout=10)

    @classmethod
    def write(cls, name, text):
        path = cls.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def prepare(self, runner):
        # Both frameworks are installed; testMatch/include and scripts determine the selected runner.
        self.write("package.json", json.dumps({"name": "regression-guard-real-fixture", "private": True,
            "scripts": {"test": "vitest run --config runner.vitest.mjs" if runner == "vitest"
                        else "jest --config runner.jest.json"},
            "devDependencies": {"vitest": "3.2.4", "jest": "30.2.0"}}))
        self.write("runner.vitest.mjs", "export default {test:{include:['cases/*.test.mjs']}};\n")
        self.write("runner.jest.json", json.dumps({"testMatch": ["<rootDir>/cases/*.test.cjs"]}))
        self.write("value.cjs", "exports.value=()=>1;\n")
        # Remove only test files this fixture created, so the other framework is not inferred.
        for name in ("cases/value.test.mjs", "cases/value.test.cjs", "cases/value named.test.mjs", "cases/value named.test.cjs"):
            (self.repo / name).unlink(missing_ok=True)
        if runner == "vitest":
            self.test = "cases/value named.test.mjs"
            self.write(self.test, "import {test,expect} from 'vitest';\n"
                       "import value from '../value.cjs';\ntest('value',()=>expect(value.value()).toBe(1));\n")
        else:
            self.test = "cases/value named.test.cjs"
            self.write(self.test, "const {value}=require('../value.cjs');\ntest('value',()=>expect(value()).toBe(1));\n")
        self.git("add", ".")
        self.git("commit", "--allow-empty", "-qm", "real runner baseline")

    def test_vitest_real_detection_selection_pass_and_failure(self):
        self.prepare("vitest")
        self.write("value.cjs", "exports.value=()=>1+0;\n")
        good = inspect(self.repo, execute=True, timeout=20)
        self.assertEqual(good["status"], "PASS", good)
        self.assertEqual(good["selected"], [self.test])
        self.write("value.cjs", "exports.value=()=>2;\n")
        bad = inspect(self.repo, execute=True, timeout=20)
        self.assertEqual(bad["status"], "FAIL", bad)

    def test_jest_real_detection_selection_pass_and_failure(self):
        self.prepare("jest")
        self.write("value.cjs", "exports.value=()=>1+0;\n")
        good = inspect(self.repo, execute=True, timeout=20)
        self.assertEqual(good["status"], "PASS", good)
        self.assertEqual(good["selected"], [self.test])
        self.write("value.cjs", "exports.value=()=>2;\n")
        bad = inspect(self.repo, execute=True, timeout=20)
        self.assertEqual(bad["status"], "FAIL", bad)


if __name__ == "__main__":
    unittest.main()
