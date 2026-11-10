"""CLI shared by all editors. analyze/report never launch runner processes."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from .engine import inspect
from .reporter import render, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="regression-guard")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("analyze", "check", "report"):
        p = sub.add_parser(name)
        p.add_argument("--repo", type=Path, required=True)
        p.add_argument("--base", help="Compare base commit to HEAD in addition to worktree changes")
        p.add_argument("--mode", choices=("fast", "targeted", "full"), default="targeted")
        p.add_argument("--json", type=Path)
        p.add_argument("--fallback", choices=("unknown", "suite"), help="Default: unknown; suite is explicit")
        p.add_argument("--max-tests", type=int, help="Maximum executed test files across all runners (default 50)")
        p.add_argument("--python-runner", choices=("auto", "pytest", "unittest"))
        p.add_argument("--compact", action="store_true", help="Bounded console output for lifecycle hooks")
        p.add_argument("--timeout", type=float, default=120, help="Total analysis/runner budget in seconds")
        if name == "check":
            p.add_argument("--allow-node-test", action="store_true",
                           help="Deprecated compatibility option; validated Node selections run automatically")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    try:
        result = inspect(args.repo, mode=args.mode, base=args.base,
                         execute=args.command == "check", timeout=args.timeout,
                         fallback=args.fallback, max_tests=args.max_tests,
                         python_runner=args.python_runner)
        if args.json:
            write_json(result, args.json)
        print(render(result, compact=args.compact))
        return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2, "UNKNOWN": 3}[result["status"]]
    except (ValueError, OSError) as exc:
        print(f"regression-guard: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
