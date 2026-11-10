"""A shared deadline and shell-free subprocesses, with bounded output and tree cleanup."""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class BudgetExceeded(TimeoutError):
    pass


class Budget:
    def __init__(self, seconds: float):
        self.started = time.monotonic()
        self.deadline = self.started + seconds

    @property
    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def check(self) -> None:
        if self.remaining <= 0:
            raise BudgetExceeded('Total analysis/runner budget exhausted.')

    @property
    def elapsed(self) -> float:
        return round(time.monotonic() - self.started, 3)


@dataclass
class ProcessResult:
    code: int | None = None
    output: str = ""
    timed_out: bool = False
    error: str = ""


def stop_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def invoke(command: list[str], cwd: Path, budget: Budget) -> ProcessResult:
    if budget.remaining <= 0:
        return ProcessResult(timed_out=True, error="Total budget exhausted before starting command.")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "NO_COLOR": "1", "CI": "1"}
    env.pop("FORCE_COLOR", None)
    try:
        with tempfile.TemporaryFile() as output:
            kwargs = {"start_new_session": True} if os.name != "nt" else {
                "creationflags": subprocess.CREATE_NO_WINDOW}
            process = subprocess.Popen(command, cwd=cwd, env=env, shell=False,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, **kwargs)
            timed_out = False
            try:
                process.wait(timeout=max(0.001, budget.remaining))
            except subprocess.TimeoutExpired:
                timed_out = True
                stop_tree(process)
            size = output.tell()
            output.seek(max(0, size - 4 * 1024 * 1024))
            text = output.read().decode("utf-8", "replace")
            if size > 4 * 1024 * 1024:
                return ProcessResult(process.returncode, text, timed_out,
                                     "Runner output exceeded 4 MiB; result cannot be verified.")
            return ProcessResult(process.returncode, text, timed_out)
    except (OSError, subprocess.SubprocessError) as exc:
        return ProcessResult(error=f"{type(exc).__name__}: {exc}")
