import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import Repository, fixture
from regression_guard.engine import inspect
from regression_guard.scripts import resolve
from regression_guard.dependencies import graph

RUNNERS = ("pytest", "unittest", "node:test", "vitest", "jest")


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.repositories = []

    def tearDown(self):
        for repo in self.repositories:
            repo.close()

    def repo(self, runner=None):
        repo = Repository()
        self.repositories.append(repo)
        if runner:
            source, test = fixture(repo, runner)
            repo.commit()
            return repo, source, test
        return repo

    def check(self, repo, **kwargs):
        return inspect(repo.path, execute=True, timeout=15, **kwargs)

    def test_detection_discovery_selection_and_execution_for_each_runner(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                repo, source, test = self.repo(runner)
                repo.write(source, (repo.path / source).read_text() + "\n// edit\n"
                           if runner not in {"pytest", "unittest"} else "def value(): return 1 + 0\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "PASS", report)
                self.assertEqual(report["selected"], [test])
                self.assertEqual(report["executed"], [test])
                self.assertEqual(report["case_counts"]["passed"], 1)
                self.assertIn(runner, [r["runner"] for r in report["runners"]])
                self.assertTrue(report["runners"][0]["selection_reasons"])

    def test_changed_test_is_selected_for_each_runner(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                repo, _, test = self.repo(runner)
                repo.write(test, (repo.path / test).read_text() + "\n")
                self.assertEqual(self.check(repo)["selected"], [test])

    def test_failure_for_each_runner(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                repo, source, test = self.repo(runner)
                if runner in {"pytest", "unittest"}:
                    repo.write(source, "def value(): return 2\n")
                elif runner == "node:test":
                    repo.write(source, "export function value() { return 2 }\n")
                else:
                    repo.write(test, (repo.path / test).read_text() + "// FAIL\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "FAIL", report)
                self.assertEqual(report["failed"], [test])

    def test_zero_cases_for_each_runner_never_passes(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                repo, _, test = self.repo(runner)
                repo.write(test, "import unittest\nclass Empty(unittest.TestCase): pass\n"
                           if runner == "unittest" else
                           "import test from 'node:test';\n" if runner == "node:test" else
                           "// EMPTY\n" if runner in {"vitest", "jest"} else "# no tests\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "UNKNOWN", report)
                self.assertEqual(report["case_counts"]["passed"], 0)

    def test_timeout_for_each_runner_leaves_pending(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                repo, _, test = self.repo(runner)
                if runner == "pytest":
                    repo.write(test, "import time\ndef test_slow(): time.sleep(3)\n")
                elif runner == "unittest":
                    repo.write(test, "import unittest,time\nclass Slow(unittest.TestCase):\n"
                               " def test_slow(self): time.sleep(3)\n")
                elif runner == "node:test":
                    repo.write(test, "import test from 'node:test';\n"
                               "test('slow', async()=>new Promise(r=>setTimeout(r,3000)));\n")
                else:
                    repo.write(test, (repo.path / test).read_text() + "// SLOW\n")
                report = inspect(repo.path, execute=True, timeout=0.8)
                self.assertEqual(report["status"], "INCOMPLETE", report)
                self.assertIn(test, report["pending"])

    def test_no_test_files_for_each_runner(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                repo, source, test = self.repo(runner)
                (repo.path / test).unlink()
                if runner in {"vitest", "jest"}:
                    # Native discovery must return an existing list, which may be empty.
                    binary = "vitest/vitest.mjs" if runner == "vitest" else "jest/bin/jest.js"
                    repo.write("node_modules/" + binary, "console.log('[]');\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "UNKNOWN", report)
                self.assertEqual(report["executed"], [])

    def test_missing_node_and_framework_binaries_are_unknown(self):
        for runner in ("node:test", "vitest", "jest"):
            with self.subTest(runner=runner):
                repo, source, _ = self.repo(runner)
                repo.write(source, "export function value() { return 1+0 }\n")
                with patch("regression_guard.adapters.javascript.shutil.which", return_value=None):
                    report = self.check(repo)
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertEqual(report["executed"], [])
        repo, source, _ = self.repo("pytest")
        repo.write(source, "def value(): return 1+0\n")
        with patch("regression_guard.adapters.python.importlib.util.find_spec", return_value=None):
            self.assertEqual(self.check(repo)["status"], "UNKNOWN")

    def test_missing_local_vitest_and_jest_do_not_download(self):
        for runner in ("vitest", "jest"):
            with self.subTest(runner=runner):
                repo, source, _ = self.repo(runner)
                binary = "vitest/vitest.mjs" if runner == "vitest" else "jest/bin/jest.js"
                (repo.path / "node_modules" / binary).unlink()
                repo.write(source, "export function value() { return 1+0 }\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertEqual(report["executed"], [])

    def test_mixed_python_node_runs_both(self):
        repo = self.repo()
        py_source, py_test = fixture(repo, "pytest")
        js_source, js_test = fixture(repo, "node:test")
        repo.commit()
        repo.write(py_source, "def value(): return 1+0\n")
        repo.write(js_source, "export function value() { return 1+0 }\n")
        report = self.check(repo)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(set(report["executed"]), {py_test, js_test})

    def test_node_patterns_and_safe_package_manager_aliases(self):
        for manager in ("npm run", "pnpm run", "yarn"):
            with self.subTest(manager=manager):
                repo, source, _ = self.repo("node:test")
                data = json.loads((repo.path / "package.json").read_text())
                data["scripts"] = {"test": manager + " unit",
                                   "unit": "node --test tests/*.{test,spec}.mjs"}
                repo.write("package.json", json.dumps(data))
                repo.write("tests/calc.spec.mjs", (repo.path / "tests/calc.test.mjs").read_text())
                repo.commit()
                repo.write(source, "export function value() { return 1+0 }\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "PASS", report)
                self.assertEqual(len(report["selected"]), 2)

    def test_node_without_package_json_is_detected(self):
        repo, source, _ = self.repo("node:test")
        (repo.path / "package.json").unlink()
        repo.commit()
        repo.write(source, "export function value() { return 1+0 }\n")
        self.assertEqual(self.check(repo)["status"], "PASS")

    def test_transitive_node_dependency_and_unrelated_test(self):
        repo, source, test = self.repo("node:test")
        repo.write("src/bridge.mjs", "export {value} from './calc.mjs';\n")
        repo.write(test, (repo.path / test).read_text().replace("../src/calc.mjs", "../src/bridge.mjs"))
        repo.write("tests/other.test.mjs", "import test from 'node:test'; test('other',()=>{});\n")
        repo.commit()
        repo.write(source, "export function value() { return 1+0 }\n")
        report = self.check(repo)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["selected"], [test])

    def test_unmapped_change_is_unknown_and_explicit_suite_fallback_is_bounded(self):
        repo, _, test = self.repo("node:test")
        repo.write("src/unrelated.mjs", "export const other=1;\n")
        self.assertEqual(self.check(repo)["status"], "UNKNOWN")
        report = self.check(repo, fallback="suite")
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["selected"], [test])
        repo.write("tests/other.test.mjs", "import test from 'node:test'; test('other',()=>{});\n")
        report = self.check(repo, fallback="suite", max_tests=1)
        self.assertEqual(report["status"], "UNKNOWN")

    def test_case_skips_do_not_produce_pass(self):
        for runner in ("node:test", "unittest", "vitest", "jest"):
            with self.subTest(runner=runner):
                repo, _, test = self.repo(runner)
                if runner == "node:test":
                    body = "import test from 'node:test'; test.skip('skipped',()=>{});\n"
                elif runner == "unittest":
                    body = "import unittest\n@unittest.skip('fixture')\nclass Skip(unittest.TestCase):\n def test_skip(self): pass\n"
                else:
                    body = (repo.path / test).read_text() + "// SKIP\n"
                repo.write(test, body)
                self.assertEqual(self.check(repo)["status"], "INCOMPLETE")

    def test_analysis_never_launches_native_discovery_or_tests(self):
        repo, source, _ = self.repo("vitest")
        repo.write(source, "export function value() { return 1+0 }\n")
        with patch("regression_guard.adapters.javascript.invoke", side_effect=AssertionError("executed")):
            report = inspect(repo.path, execute=False)
        self.assertEqual(report["executed"], [])
        self.assertEqual(report["status"], "UNKNOWN")

    def test_pytest_custom_discovery_configuration(self):
        repo = self.repo()
        repo.write("calc.py", "def value(): return 1\n")
        repo.write("checks/spec_calc.py", "from calc import value\ndef test_value(): assert value()==1\n")
        repo.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths=["checks"]\npython_files=["spec_*.py"]\n')
        repo.commit()
        repo.write("calc.py", "def value(): return 1+0\n")
        report = self.check(repo)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["discovered"], ["checks/spec_calc.py"])

    def test_policy_configuration_and_invalid_policy(self):
        repo, _, _ = self.repo("node:test")
        repo.write(".regression-guard.toml", 'fallback="suite"\nmax_tests=2\n')
        self.assertEqual(self.check(repo)["status"], "PASS")
        repo.write(".regression-guard.toml", "max_tests=0\n")
        with self.assertRaises(ValueError):
            self.check(repo)

    def test_malformed_package_json_and_unknown_runner_are_unknown(self):
        for content in ('[]', '{bad', '{"scripts":{"test":"mocha"}}', '{"dependencies":[]}', '{"dependencies":null}'):
            with self.subTest(content=content):
                repo = self.repo()
                repo.write("package.json", content)
                repo.write("src/value.js", "export const x=1;\n")
                repo.commit()
                repo.write("src/value.js", "export const x=2;\n")
                self.assertEqual(self.check(repo)["status"], "UNKNOWN")

    def test_disallowed_script_never_executes_injected_command(self):
        repo, source, _ = self.repo("node:test")
        repo.write("package.json", json.dumps({"scripts": {"test":
            "node --test tests/*.test.mjs && node -e \"require('fs').writeFileSync('PWNED','1')\""}}))
        report = self.check(repo)
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertFalse((repo.path / "PWNED").exists())
        self.assertFalse(any("npm" in arg for run in report["runners"]
                             for cmd in run["commands"] for arg in cmd))

    def test_dynamic_import_and_aliases_stay_unknown(self):
        for import_text in ("const p='./calc.mjs'; await import(p);", "import x from '@/calc';"):
            with self.subTest(import_text=import_text):
                repo, _, test = self.repo("node:test")
                repo.write(test, (repo.path / test).read_text() + import_text + "\n")
                report = self.check(repo)
                self.assertNotEqual(report["status"], "PASS")

    def test_package_subdirectory_is_supported(self):
        repo = self.repo()
        repo.write("apps/ui/package.json", json.dumps({"scripts": {"test": "node --test tests/*.test.mjs"}}))
        repo.write("apps/ui/value.mjs", "export const value=1;\n")
        repo.write("apps/ui/tests/value.test.mjs", "import test from 'node:test';\n"
                   "import {value} from '../value.mjs';\n"
                   "test('value',()=>{if(value!==1) throw Error('bad')});\n")
        repo.commit()
        repo.write("apps/ui/value.mjs", "export const value=1+0;\n")
        report = self.check(repo)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["runners"][0]["directory"], "apps/ui")

    def test_import_text_in_strings_and_regex_does_not_create_coverage(self):
        for text in ('const text = "import x from \'../src/other.mjs\'";\n',
                     'const pattern = /import x from "[.]other"/;\n'):
            with self.subTest(text=text):
                repo, _, test = self.repo("node:test")
                repo.write("src/other.mjs", "export const other=1;\n")
                repo.write(test, (repo.path / test).read_text() + text)
                repo.commit()
                repo.write("src/other.mjs", "export const other=2;\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "UNKNOWN", report)
                self.assertEqual(report["selected"], [])

    def test_pytest_adapter_preserves_legacy_fast_and_targeted_selections(self):
        from regression_guard.git_analyzer import changes
        from regression_guard.impact_analyzer import analyze
        from regression_guard.test_selector import select
        repo, source, _ = self.repo("pytest")
        repo.write("consumer.py", "from calc import value\ndef use(): return value()\n")
        repo.write("test_consumer.py", "from consumer import use\ndef test_use(): assert use()==1\n")
        repo.commit()
        repo.write(source, "def value(): return 1+0\n")
        for mode in ("fast", "targeted"):
            legacy = select(repo.path, analyze(repo.path, changes(repo.path)), mode)
            modern = inspect(repo.path, execute=False, mode=mode)
            self.assertEqual(modern["selected"], legacy.tests)

    def test_deadline_applies_before_test_execution(self):
        repo, source, _ = self.repo("node:test")
        repo.write(source, "export function value(){return 1+0}\n")
        report = inspect(repo.path, execute=True, timeout=0.00001)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["executed"], [])

    def test_global_file_budget_applies_across_runners(self):
        repo = self.repo()
        py, _ = fixture(repo, "pytest")
        js, _ = fixture(repo, "node:test")
        repo.commit()
        repo.write(py, "def value(): return 1+0\n")
        repo.write(js, "export function value(){return 1+0}\n")
        report = self.check(repo, max_tests=1)
        self.assertEqual(report["status"], "INCOMPLETE", report)
        self.assertEqual(len(report["executed"]), 1)
        self.assertEqual(len(report["pending"]), 1)

    def test_pytest_testpaths_dot_and_deselection_are_honest(self):
        repo, _, test = self.repo("pytest")
        repo.write("pytest.ini", "[pytest]\ntestpaths = .\naddopts = -k value\n")
        repo.write(test, (repo.path / test).read_text() + "\ndef test_unrelated(): assert True\n")
        repo.commit()
        repo.write("calc.py", "def value(): return 1+0\n")
        report = self.check(repo)
        self.assertIn(test, report["discovered"])
        self.assertNotEqual(report["status"], "PASS")

    def test_auxiliary_python_file_does_not_require_pytest_in_node_project(self):
        repo, source, _ = self.repo("node:test")
        repo.write("tools/helper.py", "print('not a test')\n")
        repo.commit()
        repo.write(source, "export function value(){return 1+0}\n")
        with patch("regression_guard.adapters.python.importlib.util.find_spec", return_value=None):
            report = self.check(repo)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual([r["runner"] for r in report["runners"]], ["node:test"])

    def test_framework_dependency_with_conventional_tests_identifies_runner(self):
        for runner in ("vitest", "jest"):
            with self.subTest(runner=runner):
                repo, source, _ = self.repo(runner)
                repo.write("package.json", json.dumps({"devDependencies": {runner: "fixture"}}))
                repo.commit()
                repo.write(source, "export function value(){return 1+0}\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "PASS", report)
                self.assertEqual([r["runner"] for r in report["runners"]], [runner])


    def test_incompatible_framework_output_is_unknown(self):
        for runner in ("vitest", "jest"):
            with self.subTest(runner=runner):
                repo, source, test = self.repo(runner)
                binary = "vitest/vitest.mjs" if runner == "vitest" else "jest/bin/jest.js"
                repo.write(source, "export function value(){return 1+0}\n")
                repo.write("node_modules/" + binary, "console.log('[42]');\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertEqual(report["executed"], [])
                files = json.dumps([str(repo.path / test)])
                repo.write("node_modules/" + binary,
                    "const a=process.argv.slice(2);console.log(JSON.stringify("
                    "(a.includes('list')||a.includes('--listTests'))?" + files +
                    ":{numTotalTests:2,numPassedTests:1,numFailedTests:0,numPendingTests:0}));\n")
                report = self.check(repo)
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertEqual(report["executed"], [test])



class ScriptPolicyTests(unittest.TestCase):
    def test_allowed_aliases_and_commands(self):
        for command, name in (("node --test tests/*.test.mjs", "node:test"),
                               ("vitest run --config vitest.config.mjs", "vitest"),
                               ("jest --runInBand", "jest")):
            self.assertEqual(resolve({"test": command}).runner, name)
        self.assertEqual(resolve({"test": "npm run unit", "unit": "pnpm run checks",
                                  "checks": "yarn leaf", "leaf": "node --test"}).runner, "node:test")

    def test_rejects_shell_options_external_paths_and_cycles(self):
        for command in ("node --test && evil", "npm exec jest", "npx vitest",
                        "node --test --require payload.js", "node --test ../outside.mjs",
                        "node --test C:/outside.mjs", "jest --passWithNoTests",
                        "FOO=1 vitest", "yarn test", "node --test `evil`"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                resolve({"test": command})

    def test_comment_import_is_not_a_dependency(self):
        repo = Repository()
        try:
            repo.write("x.mjs", "// import x from './missing.mjs'\n/* require('./missing.mjs') */\nexport const x=1;\n")
            edges, errors = graph(repo.path, ["x.mjs"])
            self.assertEqual(edges, {"x.mjs": set()})
            self.assertEqual(errors, {})
        finally:
            repo.close()


if __name__ == "__main__":
    unittest.main()
