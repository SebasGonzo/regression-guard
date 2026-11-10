"""Static repository inventory, package metadata and explicit policy."""
from __future__ import annotations

import os
import tomllib
import json
from pathlib import Path, PureWindowsPath

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build",
            "coverage", ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".next"}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts",
                   ".go", ".rs", ".java", ".cs", ".rb", ".php", ".vue", ".svelte",
                   ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".lock",
                   ".css", ".scss", ".sass", ".less", ".html", ".mdx"}
CONFIG_NAMES = {"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "conftest.py",
                "package.json", "tsconfig.json", "package-lock.json", "pnpm-lock.yaml",
                "yarn.lock", ".regression-guard.toml"}


def relevant(path: str) -> bool:
    p = Path(path)
    return (p.suffix.lower() in SOURCE_SUFFIXES or p.name.lower() in CONFIG_NAMES
            or (p.name.lower().startswith("requirements") and p.suffix.lower() == ".txt"))


def inventory(repo: Path, budget=None) -> list[str]:
    files = []
    for directory, names, leaves in os.walk(repo, followlinks=False):
        if budget:
            budget.check()
        names[:] = sorted(n for n in names if n not in EXCLUDED
                          and not (Path(directory) / n).is_symlink())
        for name in sorted(leaves):
            path = Path(directory) / name
            if not path.is_symlink():
                files.append(path.relative_to(repo).as_posix())
    return files


def local_path(root: Path, value: str, *, pattern: bool = False) -> str:
    value = value.replace("\\", "/")
    if (not value or Path(value).is_absolute() or PureWindowsPath(value).is_absolute()
            or PureWindowsPath(value).drive or ".." in Path(value).parts or value.startswith("-")):
        raise ValueError(f"Only relative repository paths are allowed: {value!r}")
    if not pattern and not (root / value).resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes the repository: {value!r}")
    return value


def policy_config(repo: Path) -> dict:
    path = repo / ".regression-guard.toml"
    if path.is_file():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    elif (repo / "pyproject.toml").is_file():
        data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8")).get(
            "tool", {}).get("regression_guard", {})
    else:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Regression Guard policy must be a TOML table.")
    allowed = {"fallback", "max_tests", "python_runner"}
    if set(data) - allowed:
        raise ValueError("Unsupported Regression Guard policy: " + ", ".join(sorted(set(data) - allowed)))
    return data


def packages(repo: Path, files: list[str]) -> tuple[list[dict], list[str]]:
    result, limitations = [], []
    for name in files:
        if Path(name).name != "package.json":
            continue
        try:
            data = json.loads((repo / name).read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            for field in ("scripts", "dependencies", "devDependencies"):
                if data.get(field) is None:
                    data[field] = {}
                elif not isinstance(data[field], dict):
                    raise ValueError(f"{field} must be a JSON object")
            directory = Path(name).parent.as_posix()
            root = repo / directory
            manager = str(data.get("packageManager", "")).split("@")[0]
            locks = [m for m, f in (("npm", "package-lock.json"), ("pnpm", "pnpm-lock.yaml"),
                                     ("yarn", "yarn.lock")) if (root / f).exists()]
            result.append({"directory": directory, "data": data, "manager": manager or (
                locks[0] if len(locks) == 1 else "unknown"), "locks": locks})
        except (OSError, ValueError, UnicodeError) as exc:
            limitations.append(f"Cannot read {name}: {exc}")
    return result, limitations
