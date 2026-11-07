"""Shared, bounded UserPromptSubmit/Stop hook for Claude Code and Codex."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
CONFIG_NAMES = {"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "package.json", "tsconfig.json"}


def relevant(path: str) -> bool:
    p = Path(path)
    return p.suffix.lower() in CODE_SUFFIXES or p.name.lower() in CONFIG_NAMES or (
        p.name.lower().startswith("requirements") and p.suffix.lower() == ".txt"
    )


def git(repo: Path, *args: str) -> bytes:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=10)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", "replace").strip() or "git failed")
    return p.stdout


def repository(cwd: str) -> Path | None:
    try:
        return Path(os.fsdecode(git(Path(cwd), "rev-parse", "--show-toplevel").strip())).resolve()
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return None


def snapshot(repo: Path) -> dict:
    head = git(repo, "rev-parse", "HEAD").strip().decode("ascii")
    names = set()
    for args in (("diff", "--name-only", "-z"), ("diff", "--cached", "--name-only", "-z"),
                 ("ls-files", "--others", "--exclude-standard", "-z")):
        names.update(os.fsdecode(x) for x in git(repo, *args).split(b"\0") if x)
    names = {name for name in names if relevant(name)}
    index = {}
    for item in git(repo, "ls-files", "--stage", "-z").split(b"\0"):
        if not item or b"\t" not in item:
            continue
        meta, name = item.split(b"\t", 1)
        decoded = os.fsdecode(name)
        if decoded in names:
            index[decoded] = meta.decode("ascii", "replace")
    files = {}
    for name in sorted(names):
        path = repo / name
        try:
            data = path.read_bytes() if path.is_file() else b"<missing>"
            files[name] = {"worktree": hashlib.sha256(data).hexdigest(), "index": index.get(name)}
        except OSError:
            files[name] = {"worktree": "<unreadable>", "index": index.get(name)}
    return {"head": head, "files": files}


def state_path(agent: str, session: str, repo: Path) -> Path:
    key = hashlib.sha256(f"{agent}\0{session}\0{repo}".encode()).hexdigest()
    directory = Path(tempfile.gettempdir()) / "regression-guard-hooks"
    directory.mkdir(mode=0o700, exist_ok=True)
    return directory / f"{key}.json"


def output(agent: str, message: str | None = None) -> None:
    if message is None:
        print("{}")
    elif agent == "claude":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": message}}))
    else:
        print(json.dumps({"decision": "block", "reason": message}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=("claude", "codex"), required=True)
    parser.add_argument("--phase", choices=("start", "stop"), required=True)
    args = parser.parse_args()
    try:
        event = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        output(args.agent)
        return 0
    if os.environ.get("REGRESSION_GUARD_DISABLE", "").lower() in {"1", "true", "yes"}:
        output(args.agent)
        return 0
    if (Path.home() / ".regression-guard.disabled").exists():
        output(args.agent)
        return 0
    if args.phase == "stop" and event.get("stop_hook_active"):
        output(args.agent)
        return 0
    session = event.get("session_id")
    cwd = event.get("cwd")
    if not isinstance(session, str) or not session or not isinstance(cwd, str):
        output(args.agent)
        return 0
    repo = repository(cwd)
    if repo is None:
        output(args.agent)
        return 0
    state = state_path(args.agent, session, repo)
    claim = state.with_suffix(".claimed")
    if args.phase == "start":
        try:
            before = snapshot(repo)
            staged = state.with_suffix(".tmp")
            staged.write_text(json.dumps(before), encoding="utf-8")
            os.replace(staged, state)
            claim.unlink(missing_ok=True)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            state.unlink(missing_ok=True)
        output(args.agent)
        return 0
    try:
        before = json.loads(state.read_text(encoding="utf-8"))
        after = snapshot(repo)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        output(args.agent)
        return 0
    committed = set()
    if before["head"] != after["head"]:
        try:
            committed = {os.fsdecode(x) for x in git(repo, "diff", "--name-only", "-z", before["head"], after["head"]).split(b"\0") if x}
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            committed = set()
    if before["files"] == after["files"] and not any(relevant(x) for x in committed):
        output(args.agent)
        return 0
    try:
        fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    except FileExistsError:
        output(args.agent)
        return 0
    try:
        timeout = max(1, min(float(os.environ.get("REGRESSION_GUARD_TIMEOUT", "120")), 150))
    except ValueError:
        timeout = 120
    command = [sys.executable, str(SOURCE / "scripts" / "run.py"), "check", "--repo", str(repo),
               "--mode", "targeted", "--timeout", str(timeout)]
    if before["head"] != after["head"]:
        command += ["--base", before["head"]]
    try:
        proc = subprocess.run(command, cwd=repo, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout + 20)
        report = proc.stdout.strip()[-2500:] or proc.stderr.strip()[-1000:]
        if proc.returncode not in {0, 1, 2, 3}:
            report = f"Regression Guard: UNKNOWN (runner error {proc.returncode}). {report}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        report = f"Regression Guard: INCOMPLETE ({type(exc).__name__}: {exc})"
    output(args.agent, report + "\nReport this result to the user. Do not change code automatically to repair a failure. Do not run Regression Guard again for this task.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
