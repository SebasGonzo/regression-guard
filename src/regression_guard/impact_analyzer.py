"""Conservative Python import graph and change risk."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .git_analyzer import Change


@dataclass
class Impact:
    changed: list[str]
    dependents: list[str]
    risk: str
    unknown: bool
    limitations: list[str]


def _module(path: str) -> str:
    bits = list(Path(path).with_suffix("").parts)
    if bits and bits[0] == "src":
        bits.pop(0)
    if bits and bits[-1] == "__init__":
        bits.pop()
    return ".".join(bits)


def analyze(repo: Path, changes: list[Change]) -> Impact:
    changed = sorted({c.path for c in changes})
    python_changes = {p for p in changed if p.endswith(".py")}
    modules = {_module(p): p for p in python_changes}
    dependents: set[str] = set()
    limitations: list[str] = []
    unknown = False
    critical = {"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "conftest.py", "package.json"}
    if any(Path(p).name in critical for p in changed):
        unknown = True
        limitations.append("Global test/build configuration changed; selective coverage may be insufficient.")
    for file in repo.rglob("*.py"):
        if any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in file.parts):
            continue
        rel = file.relative_to(repo).as_posix()
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeError, OSError):
            unknown = True
            limitations.append(f"Cannot parse imports: {rel}")
            continue
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = _module(rel).split(".")[:-node.level]
                    prefix = ".".join(parent + ([node.module] if node.module else []))
                else:
                    prefix = node.module or ""
                imported.add(prefix)
                imported.update(f"{prefix}.{a.name}".strip(".") for a in node.names)
        if rel not in python_changes and any(
            imp == mod or imp.startswith(mod + ".") or mod.startswith(imp + ".")
            for imp in imported for mod in modules if imp
        ):
            dependents.add(rel)
    if any(p.endswith((".js", ".jsx", ".ts", ".tsx")) for p in changed):
        unknown = True
        limitations.append("JavaScript/TypeScript dependency mapping is not implemented.")
    if any(p.endswith(".py") and not (repo / p).exists() for p in changed):
        unknown = True
        limitations.append("Deleted or renamed Python modules may have unresolved consumers.")
    if not changed:
        limitations.append("No changes detected.")
    risk = "high" if unknown or len(dependents) > 5 else "medium" if dependents or len(changed) > 3 else "low"
    return Impact(changed, sorted(dependents), risk, unknown, sorted(set(limitations)))
