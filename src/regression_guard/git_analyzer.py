"""Read-only Git inventory. Paths are decoded from NUL records, never split on whitespace."""
from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Change:
    path: str
    status: str
    source: str
    old_path: str | None = None


def _git(repo: Path, *args: str) -> bytes:
    p = subprocess.run(["git", "-C", str(repo), *args], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=30, check=False)
    if p.returncode:
        raise ValueError(p.stderr.decode("utf-8", "replace").strip() or "Git failed")
    return p.stdout


def root(repo: Path) -> Path:
    return Path(os.fsdecode(_git(repo, "rev-parse", "--show-toplevel").strip())).resolve()


def _diff(repo: Path, source: str, *args: str) -> list[Change]:
    fields = _git(repo, "diff", "--name-status", "-z", "--find-renames", *args).split(b"\0")
    result: list[Change] = []
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i].decode("ascii", "replace")
        i += 1
        first = os.fsdecode(fields[i]); i += 1
        old = None
        if status[0] in "RC":
            old, first = first, os.fsdecode(fields[i]); i += 1
        result.append(Change(first, status[0], source, old))
    return result


def changes(repo: Path, base: str | None = None) -> list[Change]:
    repo = root(repo)
    found = _diff(repo, "staged", "--cached") + _diff(repo, "unstaged")
    if base:
        # A commit-ish is passed as an argv item. Verify it resolves to a commit.
        commit = _git(repo, "rev-parse", "--verify", f"{base}^{{commit}}").strip().decode("ascii")
        found += _diff(repo, "base", commit, "HEAD")
    raw = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    found += [Change(os.fsdecode(x), "A", "untracked") for x in raw.split(b"\0") if x]
    return sorted(set(found), key=lambda c: (c.path, c.source, c.status))


def serialize(items: list[Change]) -> list[dict]:
    return [asdict(item) for item in items]
