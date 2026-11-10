"""Bounded pytest execution, one selected file at a time for pending accounting."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Run:
    executed: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    duration: float = 0.0
    errors: list[str] = field(default_factory=list)
    timed_out: bool = False
    case_counts: dict[str, int] = field(default_factory=lambda: dict(total=0, passed=0, failed=0, skipped=0))
    commands: list[list[str]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


def run_pytest(repo: Path, tests: list[str], timeout: float) -> Run:
    result = Run(pending=tests.copy())
    start = time.monotonic()
    for test in tests:
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            result.timed_out = True
            break
        # -p no:cacheprovider avoids pytest's usual .pytest_cache writes.
        # PYTHONDONTWRITEBYTECODE avoids bytecode writes in the analyzed repo.
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        try:
            p = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", test],
                               cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", timeout=remaining)
        except subprocess.TimeoutExpired:
            result.timed_out = True
            result.errors.append(f"Timeout while running {test}")
            break
        result.pending.remove(test)
        result.executed.append(test)
        if p.returncode == 0:
            result.passed.append(test)
        elif p.returncode == 5:
            result.skipped.append(test)
        else:
            result.failed.append(test)
            result.errors.append(f"{test}: {p.stdout[-4000:]}")
    result.duration = round(time.monotonic() - start, 3)
    return result
