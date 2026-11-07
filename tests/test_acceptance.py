import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from regression_guard.git_analyzer import changes
from regression_guard.impact_analyzer import analyze
from regression_guard.reporter import build
from regression_guard.test_runner import run_pytest
from regression_guard.test_selector import select


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="Regression Guard ")
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "auth.py").write_text("def valid(): return True\n")
        (self.repo / "consumer.py").write_text("import auth\ndef use(): return auth.valid()\n")
        (self.repo / "test_auth.py").write_text("import auth\ndef test_auth(): assert auth.valid()\n")
        (self.repo / "test_consumer.py").write_text("import consumer\ndef test_consumer(): assert consumer.use()\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "initial")

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, mode="targeted"):
        c = changes(self.repo)
        i = analyze(self.repo, c)
        return c, i, select(self.repo, i, mode)

    def test_clean_change_and_regression(self):
        (self.repo / "auth.py").write_text("def valid(): return 1 == 1\n")
        c, i, s = self.plan()
        self.assertEqual(s.tests, ["test_auth.py", "test_consumer.py"])
        good = run_pytest(self.repo, s.tests, 30)
        self.assertEqual(build(c, i, s, good)["status"], "PASS")
        (self.repo / "auth.py").write_text("def valid(): return False\n")
        bad = run_pytest(self.repo, s.tests, 30)
        self.assertEqual(build(c, i, s, bad)["status"], "FAIL")

    def test_fast_excludes_consumer_and_targeted_includes_it(self):
        (self.repo / "auth.py").write_text("def valid(): return False\n")
        self.assertEqual(self.plan("fast")[2].tests, ["test_auth.py"])
        self.assertEqual(self.plan("targeted")[2].tests, ["test_auth.py", "test_consumer.py"])

    def test_untracked_renamed_staged_unstaged_and_base(self):
        git(self.repo, "mv", "consumer.py", "new consumer.py")
        (self.repo / "auth.py").write_text("def valid(): return False\n")
        (self.repo / "new file.py").write_text("x = 1\n")
        c = changes(self.repo, "HEAD")
        self.assertTrue(any(x.status == "R" and x.old_path == "consumer.py" and x.path == "new consumer.py" for x in c))
        self.assertTrue(any(x.path == "auth.py" and x.source == "unstaged" for x in c))
        self.assertTrue(any(x.path == "new file.py" and x.source == "untracked" for x in c))

    def test_no_tests_unknown_and_unparsable_import(self):
        for path in self.repo.glob("test_*.py"):
            path.unlink()
        (self.repo / "consumer.py").write_text("def broken(:\n")
        (self.repo / "auth.py").write_text("def valid(): return False\n")
        c, i, s = self.plan()
        self.assertTrue(i.unknown)
        self.assertEqual(build(c, i, s, None)["status"], "UNKNOWN")

    def test_timeout_has_pending(self):
        (self.repo / "test_auth.py").write_text("import time\ndef test_auth(): time.sleep(2)\n")
        r = run_pytest(self.repo, ["test_auth.py", "test_consumer.py"], 0.2)
        self.assertTrue(r.timed_out)
        self.assertEqual(r.pending, ["test_auth.py", "test_consumer.py"])


if __name__ == "__main__":
    unittest.main()
