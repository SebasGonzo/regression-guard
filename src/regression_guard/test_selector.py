"""Select by imports first, then conventional module/test names."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .impact_analyzer import Impact


@dataclass
class Selection:
    tests: list[str]
    limitations: list[str]
    strategy: str


def select(repo: Path, impact: Impact, mode: str, *, all_tests: list[str] | None = None) -> Selection:
    all_tests = all_tests if all_tests is not None else sorted({p.relative_to(repo).as_posix() for p in repo.rglob("test_*.py")
                        if not any(x in {".venv", "venv", "node_modules", ".git"} for x in p.parts)} |
                       {p.relative_to(repo).as_posix() for p in repo.rglob("*_test.py")
                        if not any(x in {".venv", "venv", "node_modules", ".git"} for x in p.parts)})
    if mode == "full":
        return Selection(all_tests, [] if all_tests else ["No pytest tests found."], "full")
    changed = set(impact.changed)
    relevant = changed | (set(impact.dependents) if mode == "targeted" else set())
    selected: set[str] = set()
    for test in all_tests:
        if test in relevant:
            selected.add(test)
            continue
        test_stem = Path(test).stem.removeprefix("test_").removesuffix("_test")
        for path in relevant:
            stem = Path(path).stem.removeprefix("test_").removesuffix("_test")
            if stem and (test_stem == stem or test_stem.startswith(stem + "_")):
                selected.add(test)
    limitations = impact.limitations.copy()
    if not selected and all_tests and impact.changed:
        limitations.append("No related tests identified; impact is unknown.")
    if not all_tests:
        limitations.append("No pytest tests found.")
    return Selection(sorted(selected), limitations, mode)
