from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .git_analyzer import changes, root
from .impact_analyzer import analyze
from .reporter import build, render, write_json
from .test_runner import run_node_test, run_pytest
from .test_selector import select


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="regression-guard")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("analyze", "check", "report"):
        p = sub.add_parser(name)
        p.add_argument("--repo", type=Path, required=True)
        p.add_argument("--base", help="Compare base commit to HEAD in addition to worktree changes")
        p.add_argument("--mode", choices=("fast", "targeted", "full"), default="targeted")
        p.add_argument("--json", type=Path, help="Write JSON report to this path")
        if name == "check":
            p.add_argument("--timeout", type=float, default=120, help="Total seconds (default 120)")
            p.add_argument("--allow-node-test", action="store_true", help="Run only an exact package.json script of 'node --test'")
    args = parser.parse_args(argv)
    try:
        repo = root(args.repo)
        items = changes(repo, args.base)
        impact = analyze(repo, items)
        selection = select(repo, impact, args.mode)
        package = repo / "package.json"
        node_script = False
        if package.exists():
            try:
                import json
                scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
                if isinstance(scripts, dict) and isinstance(scripts.get("test"), str):
                    node_script = scripts["test"] == "node --test"
                    if not node_script:
                        selection.limitations.append(f"JavaScript test script detected but not executed: {scripts['test']}")
                    elif args.command != "check" or not args.allow_node_test:
                        selection.limitations.append("Safe Node test script found; use check --allow-node-test to run it.")
            except (ValueError, UnicodeError, OSError):
                selection.limitations.append("package.json could not be parsed; JavaScript test strategy unknown.")
        run = None
        if args.command == "check":
            if args.timeout <= 0:
                parser.error("--timeout must be positive")
            if args.allow_node_test and node_script:
                if selection.tests:
                    selection.limitations.append("Python and Node tests both exist; run separately to keep the time budget explicit.")
                else:
                    selection.tests = ["package.json:test"]
                    run = run_node_test(repo, args.timeout)
            if run is None:
                run = run_pytest(repo, selection.tests, args.timeout) if selection.tests else None
        result = build(items, impact, selection, run)
        if args.json:
            write_json(result, args.json)
        print(render(result))
        return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2, "UNKNOWN": 3}[result["status"]]
    except (ValueError, OSError) as exc:
        print(f"regression-guard: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
