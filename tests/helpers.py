"""Temporary Git repositories owned by Regression Guard's tests."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


class Repository:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Regression Guard fixture ")
        self.path = Path(self.temp.name).resolve()
        self.git("init", "-q")
        self.git("config", "user.name", "Regression Guard Test")
        self.git("config", "user.email", "test@example.invalid")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.path), *args],
                              check=True, capture_output=True, timeout=10)

    def write(self, name, text):
        path = self.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "--allow-empty", "-qm", "fixture baseline")

    def close(self):
        self.temp.cleanup()


def fixture(repo: Repository, runner: str):
    if runner in {"pytest", "unittest"}:
        repo.write("calc.py", "def value(): return 1\n")
        if runner == "pytest":
            repo.write("test_calc.py", "from calc import value\ndef test_value(): assert value() == 1\n")
        else:
            repo.write("test_calc.py", "import unittest\nfrom calc import value\n"
                       "class ValueTests(unittest.TestCase):\n"
                       "    def test_value(self): self.assertEqual(value(), 1)\n")
        return "calc.py", "test_calc.py"
    extension = "mjs" if runner == "node:test" else "js"
    source, test = "src/calc.mjs", f"tests/calc.test.{extension}"
    repo.write(source, "export function value() { return 1 }\n")
    if runner == "node:test":
        body = "import test from 'node:test'; import assert from 'node:assert/strict';\n"
        body += "import {value} from '../src/calc.mjs';\ntest('value', () => assert.equal(value(), 1));\n"
        script = "node --test tests/*.test.mjs"
    else:
        body = "import {value} from '../src/calc.mjs';\n// PASS fixture for runner contract\n"
        script = runner + " run" if runner == "vitest" else runner
        binary = "vitest/vitest.mjs" if runner == "vitest" else "jest/bin/jest.js"
        # This is a contract fixture, not an installation of Vitest/Jest.
        stub = "import('node:fs').then(fs => {\nconst args=process.argv.slice(2);\n"
        stub += "const files=" + json.dumps([str(repo.path / test)]) + ";\n"
        stub += "if(args.includes('list') || args.includes('--listTests')) { console.log(JSON.stringify(files)); return; }\n"
        stub += "const path=args.find(x => /\\.test\\./.test(x));\n"
        stub += "const body=fs.readFileSync(path,'utf8');\n"
        stub += "const fail=body.includes('FAIL'), empty=body.includes('EMPTY'), skip=body.includes('SKIP');\n"
        stub += "const out={numTotalTests:empty?0:1,numPassedTests:empty||fail||skip?0:1,"
        stub += "numFailedTests:fail?1:0,numPendingTests:skip?1:0};\n"
        stub += "if(body.includes('SLOW')) setTimeout(()=>console.log(JSON.stringify(out)),3000);"
        stub += "else {console.log(JSON.stringify(out)); process.exitCode=fail?1:0;}\n});\n"
        repo.write("node_modules/" + binary, stub)
    repo.write(test, body)
    repo.write("package.json", json.dumps({"scripts": {"test": script}, "type": "module",
                                          "packageManager": "pnpm@10.0.0"}))
    return source, test
