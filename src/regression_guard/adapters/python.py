"""Independent pytest and standard-library unittest adapters."""
from __future__ import annotations

import ast
import configparser
import fnmatch
import importlib.util
import shlex
import sys
import tomllib
from pathlib import Path

from .base import Context, Plan, apply_fallback
from ..execution import execute_files
from ..impact_analyzer import analyze
from ..test_selector import select

PY_CONFIG = {"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "conftest.py",
             ".regression-guard.toml"}


def configuration(context: Context) -> tuple[dict, bool, list[str]]:
    repo = context.repo
    errors = []
    for filename, section in (("pytest.ini", "pytest"), ("pyproject.toml", ""),
                              ("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        path = repo / filename
        if not path.is_file():
            continue
        try:
            if filename == "pyproject.toml":
                settings = tomllib.loads(path.read_text(encoding="utf-8")).get(
                    "tool", {}).get("pytest", {}).get("ini_options")
                if settings is not None:
                    return settings, True, errors
            else:
                parser = configparser.ConfigParser(interpolation=None)
                parser.read_string(path.read_text(encoding="utf-8"))
                if parser.has_section(section):
                    return dict(parser[section]), True, errors
        except (OSError, ValueError, configparser.Error) as exc:
            errors.append(f"Cannot read {filename}: {exc}")
    return {}, False, errors


def words(value) -> list[str]:
    return list(value) if isinstance(value, list) else shlex.split(str(value))


def unittest_file(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, SyntaxError, UnicodeError):
        return False
    aliases = {"TestCase"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "unittest":
            aliases.update(x.asname or x.name for x in node.names if x.name == "TestCase")
    return any(isinstance(node, ast.ClassDef) and any(
        (isinstance(base, ast.Attribute) and base.attr == "TestCase")
        or (isinstance(base, ast.Name) and base.id in aliases) for base in node.bases)
        for node in ast.walk(tree))


def python_tests(context: Context) -> tuple[list[str], str, list[str]]:
    config, explicit, errors = configuration(context)
    patterns = words(config.get("python_files", ["test_*.py", "*_test.py"]))
    roots = words(config.get("testpaths", []))
    excluded = words(config.get("norecursedirs", []))
    tests = [p for p in context.files if Path(p).suffix == ".py"
             and any(fnmatch.fnmatch(Path(p).name, pattern) for pattern in patterns)
             and (not roots or "." in roots or any(p == r or fnmatch.fnmatch(p, r.rstrip("/") + "/*") for r in roots))
             and not any(fnmatch.fnmatch(part, pattern) for part in Path(p).parts for pattern in excluded)]
    runner = context.policy.python_runner
    if runner == "auto":
        runner = "pytest" if explicit or not tests or not all(
            unittest_file(context.repo / p) for p in tests) else "unittest"
    # Filtering configured by pytest is coverage uncertainty, even on exit code 0.
    opts = words(config.get("addopts", ""))
    if any(x in {"-k", "-m", "--deselect"} or x.startswith(("--deselect=", "-k=", "-m="))
           for x in opts):
        errors.append("pytest configuration filters test cases; file selection is not full case coverage.")
    return sorted(tests), runner, errors


class PythonAdapter:
    name = ""

    def detect(self, context: Context) -> list[Plan]:
        tests, runner, errors = python_tests(context)
        has_python = any(p.endswith(".py") for p in context.files) or any(
            Path(p).name in PY_CONFIG for p in context.changed)
        if not has_python or runner != self.name:
            return []
        if (not tests and context.policy.python_runner == "auto"
                and not any(p.endswith(".py") for p in context.changed)
                and not configuration(context)[1]):
            return []
        plan = Plan(self.name, discovered=tests, limitations=errors, unknown=bool(errors))
        if self.name == "pytest" and importlib.util.find_spec("pytest") is None:
            plan.available = False
            plan.unknown = True
            plan.limitations.append("pytest is not installed in the engine's Python interpreter.")
        return [plan]

    def prepare(self, context: Context, plan: Plan) -> None:
        changes = [c for c in context.changes if c.path.endswith(".py")
                   or Path(c.path).name in PY_CONFIG
                   or Path(c.path).name.startswith("requirements")]
        impact = analyze(context.repo, changes, files=context.files, budget=context.budget)
        selection = select(context.repo, impact, context.mode, all_tests=plan.discovered)
        plan.selected = selection.tests
        plan.limitations.extend(selection.limitations)
        plan.unknown |= impact.unknown
        plan.metadata["dependents"] = impact.dependents
        for test in plan.selected:
            plan.reasons[test] = ["explicit full mode" if context.mode == "full" else
                                  "changed test or Python import/name relationship"]
        if context.mode == "full" and plan.discovered:
            plan.covered.update(c.path for c in changes)
        else:
            for change in changes:
                if context.budget.remaining <= 0:
                    plan.unknown = True
                    plan.limitations.append("Budget exhausted while mapping Python changes.")
                    break
                single = analyze(context.repo, [change], files=context.files, budget=context.budget)
                related = select(context.repo, single, context.mode, all_tests=plan.discovered).tests
                if related and not single.unknown:
                    plan.covered.add(change.path)
        apply_fallback(context, plan, {c.path for c in changes} - plan.covered)
        if not plan.discovered:
            plan.limitations.append(f"No {self.name} test files discovered.")

    def run(self, context: Context, plan: Plan):
        if self.name == "pytest":
            return execute_files(context, plan, lambda test: [
                sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "./" + test])
        return execute_files(context, plan, lambda test: [
            sys.executable, "-m", "unittest", "discover", "-s",
            str(Path(test).parent), "-p", Path(test).name, "-v"])


class PytestAdapter(PythonAdapter):
    name = "pytest"


class UnittestAdapter(PythonAdapter):
    name = "unittest"
