"""Independent pytest and standard-library unittest adapters."""
from __future__ import annotations

import ast
import configparser
import fnmatch
import importlib.util
import os
import shutil
import shlex
import sys
import tomllib
from pathlib import Path

from .base import Context, Plan, apply_fallback, apply_mappings, configure_environment
from ..execution import execute_files
from ..git_analyzer import Change
from ..impact_analyzer import analyze, import_index
from ..project import owner
from ..test_selector import select

PY_PROJECT = {"pyproject.toml", "pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini",
              "setup.cfg", "tox.ini", "setup.py", "requirements.txt"}
PY_CONFIG = PY_PROJECT | {"conftest.py",
             ".regression-guard.toml"}


def configuration(repo: Path) -> tuple[dict, bool, list[str]]:
    errors = []
    for filename, section in (("pytest.toml", "pytest"), (".pytest.toml", "pytest"),
                              ("pytest.ini", "pytest"), (".pytest.ini", "pytest"), ("pyproject.toml", ""),
                              ("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        path = repo / filename
        if not path.is_file():
            continue
        try:
            if filename.endswith(".toml"):
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                pytest_config = data.get("tool", {}).get("pytest", {})
                settings = (pytest_config.get("ini_options", pytest_config or None)
                            if filename == "pyproject.toml" else data.get(section))
                if settings is not None:
                    if isinstance(settings, dict):
                        return settings, True, errors
                    raise ValueError("expected a pytest configuration table")
            else:
                parser = configparser.ConfigParser(interpolation=None)
                parser.read_string(path.read_text(encoding="utf-8"))
                if parser.has_section(section) or filename.endswith("pytest.ini"):
                    return dict(parser[section]) if parser.has_section(section) else {}, True, errors
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


def python_tests(repo: Path, files: list[str], preferred: str) -> tuple[list[str], str, list[str], bool]:
    config, explicit, errors = configuration(repo)
    patterns = words(config.get("python_files", ["test_*.py", "*_test.py"]))
    roots = words(config.get("testpaths", []))
    excluded = words(config.get("norecursedirs", []))
    tests = [p for p in files if Path(p).suffix == ".py"
             and any(fnmatch.fnmatch(Path(p).name, pattern) for pattern in patterns)
             and (not roots or "." in roots or any(p == r or fnmatch.fnmatch(p, r.rstrip("/") + "/*") for r in roots))
             and not any(fnmatch.fnmatch(part, pattern) for part in Path(p).parts for pattern in excluded)]
    runner = preferred
    if runner == "auto":
        runner = "pytest" if explicit or not tests or not all(
            unittest_file(repo / p) for p in tests) else "unittest"
    # Filtering configured by pytest is coverage uncertainty, even on exit code 0.
    opts = words(config.get("addopts", ""))
    if any(x in {"-k", "-m", "--deselect"} or x.startswith(("--deselect=", "-k=", "-m="))
           for x in opts):
        errors.append("pytest configuration filters test cases; file selection is not full case coverage.")
    return sorted(tests), runner, errors, explicit


def python_projects(context: Context) -> dict[str, list[str]]:
    if not hasattr(context, "_python_projects"):
        directories = {Path(p).parent.as_posix() for p in context.files if Path(p).name in PY_PROJECT}
        directories.update(context.settings.get("environments", {}))
        projects: dict[str, list[str]] = {directory: [] for directory in sorted(directories | {"."})}
        for path in context.files:
            context.budget.check()
            if path.endswith(".py") or Path(path).name in PY_CONFIG:
                directory = owner(path, directories)
                projects[directory].append(Path(path).relative_to(directory).as_posix())
        context._python_projects = projects
    return context._python_projects


def python_environment(context: Context, plan: Plan) -> None:
    configure_environment(context, plan)
    if not plan.available:
        return
    explicit = plan.environment.get("venv")
    project = context.repo / plan.directory
    candidates = [context.repo / explicit] if explicit else [project / ".venv", project / "venv"]
    for venv in candidates:
        if explicit or (venv / "pyvenv.cfg").is_file():
            executable = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            plan.environment.update(source="venv", interpreter=str(executable))
            if venv.resolve().is_relative_to(context.repo) and (venv / "pyvenv.cfg").is_file():
                target = executable.resolve()
                if executable.is_file() and (target.is_relative_to(context.repo)
                                             or target == Path(sys._base_executable).resolve()):
                    return
                # A POSIX venv can point at another Python version already available on PATH.
                if executable.is_file() and os.name != "nt":
                    parts = target.name.removeprefix("python").split(".")
                    available = shutil.which(target.name) if target.name.startswith("python") and all(
                        part.isdigit() for part in parts) else None
                    if available and Path(available).resolve() == target:
                        return
            plan.limitations.append("Configured Python virtual environment is unavailable.")
            break
    else:
        plan.environment.update(source="current_python", interpreter=sys.executable)
        if plan.runner != "pytest" or importlib.util.find_spec("pytest") is not None:
            return
        plan.limitations.append("pytest is not installed in the current Python interpreter.")
    plan.available = False
    plan.unavailable_reason = "environment_unavailable"


class PythonAdapter:
    name = ""

    def detect(self, context: Context) -> list[Plan]:
        result = []
        projects = python_projects(context)
        if not hasattr(context, "_python_tests"):
            context._python_tests = {
                directory: python_tests(context.repo / directory, files, context.policy.python_runner)
                for directory, files in projects.items() if files
            }
        for directory, (tests, runner, errors, configured) in context._python_tests.items():
            has_changes = any(path.endswith(".py") and owner(path, projects) == directory
                              for path in context.changed)
            if runner != self.name or not (tests or configured or has_changes):
                continue
            plan = Plan(self.name, directory, limitations=errors.copy(), unknown=bool(errors))
            plan.discovered = [(Path(directory) / p).as_posix() for p in tests]
            python_environment(context, plan)
            result.append(plan)
        return result

    def prepare(self, context: Context, plan: Plan) -> None:
        apply_mappings(context, plan)
        projects = python_projects(context)
        directory = Path(plan.directory)
        repo = context.repo / directory
        changes = [c for c in context.changes if c.path not in plan.covered
                   and owner(c.path, projects) == plan.directory
                   and (c.path.endswith(".py") or Path(c.path).name in PY_CONFIG
                        or Path(c.path).name.startswith("requirements"))]
        local_changes = [Change(Path(c.path).relative_to(directory).as_posix(), c.status, c.source)
                         for c in changes]
        tests = [Path(p).relative_to(directory).as_posix() for p in plan.discovered]
        index = import_index(repo, files=projects[plan.directory], budget=context.budget) if changes else ({}, [])
        impact = analyze(repo, local_changes, budget=context.budget, index=index)
        selection = select(repo, impact, context.mode, all_tests=tests)
        inferred = [(directory / test).as_posix() for test in selection.tests]
        plan.selected = sorted(set(plan.selected) | set(inferred))
        if changes:
            plan.limitations.extend(selection.limitations)
        plan.unknown |= impact.unknown
        plan.metadata["dependents"] = [(directory / p).as_posix() for p in impact.dependents]
        for test in inferred:
            plan.reasons.setdefault(test, []).append("explicit full mode" if context.mode == "full" else
                                                    "changed test or Python import/name relationship")
        if context.mode == "full" and plan.discovered:
            plan.covered.update(c.path for c in changes)
        else:
            for change, local_change in zip(changes, local_changes):
                if context.budget.remaining <= 0:
                    plan.unknown = True
                    plan.limitations.append("Budget exhausted while mapping Python changes.")
                    break
                single = analyze(repo, [local_change], budget=context.budget, index=index)
                related = select(repo, single, context.mode, all_tests=tests).tests
                if related and not single.unknown:
                    plan.covered.add(change.path)
        apply_fallback(context, plan, {c.path for c in changes} - plan.covered)
        if not plan.discovered:
            plan.limitations.append(f"No {self.name} test files discovered.")

    def run(self, context: Context, plan: Plan):
        executable = plan.environment["interpreter"]
        directory = Path(plan.directory)
        if self.name == "pytest":
            return execute_files(context, plan, lambda test: [
                executable, "-m", "pytest", "-p", "no:cacheprovider", "-q",
                "./" + Path(test).relative_to(directory).as_posix()])
        return execute_files(context, plan, lambda test: [
            executable, "-m", "unittest", "discover", "-s",
            str(Path(test).relative_to(directory).parent), "-p", Path(test).name, "-v"])


class PytestAdapter(PythonAdapter):
    name = "pytest"


class UnittestAdapter(PythonAdapter):
    name = "unittest"
