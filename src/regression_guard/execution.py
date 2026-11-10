"""Account for actual runner results, including zero cases and partial execution."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from .process import invoke
from .test_runner import Run


@dataclass
class Counts:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def json_value(output: str, expected: type):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", output):
        try:
            value, _ = decoder.raw_decode(output[match.start():])
        except ValueError:
            continue
        if isinstance(value, expected):
            return value
    raise ValueError("Runner did not emit a usable JSON result.")


def counts(output: str, runner: str) -> Counts:
    if runner == "node:test":
        def number(label):
            found = re.findall(r"(?m)^# " + label + r" (\d+)\s*$", output)
            return int(found[-1]) if found else 0
        result = Counts(number("tests"), number("pass"), number("fail"),
                        number("skipped") + number("todo") + number("cancelled"))
        # Node can count an empty script as one successful file wrapper.
        if result.total == 1 and re.search(r"(?m)^# Subtest: .*\.(?:mjs|cjs|js)\s*$", output):
            return Counts()
        return result
    if runner in {"vitest", "jest"}:
        data = json_value(output, dict)
        return Counts(int(data.get("numTotalTests", 0)), int(data.get("numPassedTests", 0)),
                      int(data.get("numFailedTests", 0)), int(data.get("numPendingTests", 0))
                      + int(data.get("numTodoTests", 0)))
    if runner == "unittest":
        found = re.search(r"Ran (\d+) tests?", output)
        total = int(found.group(1)) if found else 0
        def unit(label):
            found = re.search(label + r"=(\d+)", output)
            return int(found.group(1)) if found else 0
        failed = unit("failures") + unit("errors") + unit("unexpected successes")
        skipped = unit("skipped") + unit("expected failures")
        return Counts(total, max(0, total - failed - skipped), failed, skipped)
    def pytest_number(label):
        found = re.search(r"(\d+) " + label, output)
        return int(found.group(1)) if found else 0
    passed, failed, skipped = (pytest_number(x) for x in ("passed", "failed", "skipped"))
    skipped += sum(pytest_number(x) for x in ("deselected", "xfailed", "xpassed"))
    return Counts(passed + failed + skipped, passed, failed, skipped)


def execute_files(context, plan, command: Callable[[str], list[str]]) -> Run:
    result = Run(pending=plan.selected.copy())
    for test in plan.selected:
        if len(result.executed) >= context.policy.max_tests or context.budget.remaining <= 0:
            result.timed_out = context.budget.remaining <= 0
            result.errors.append("Total time or file budget exhausted; remaining files were not executed.")
            break
        argv = command(test)
        result.commands.append(argv)
        process = invoke(argv, context.repo / plan.directory, context.budget)
        if process.timed_out:
            result.timed_out = True
            result.errors.append(f"Timeout while running {plan.runner}: {test}")
            break
        if process.error or process.code is None:
            result.unknown.append(f"{test}: {process.error or 'runner unavailable'}")
            break
        result.pending.remove(test)
        result.executed.append(test)
        try:
            observed = counts(process.output, plan.runner)
        except (ValueError, TypeError, KeyError) as exc:
            result.unknown.append(f"{test}: {exc}")
            if process.code:
                result.failed.append(test)
                result.errors.append(process.output[-4000:])
            continue
        for key in ("total", "passed", "failed", "skipped"):
            result.case_counts[key] += getattr(observed, key)
        if observed.total != observed.passed + observed.failed + observed.skipped:
            result.unknown.append(f"{test}: runner summary does not account for all cases.")
        if observed.failed or (process.code and not (plan.runner == "pytest" and process.code == 5)):
            result.failed.append(test)
            result.errors.append(f"{test}: {process.output[-4000:]}")
        elif not observed.total:
            result.unknown.append(f"{test}: runner completed without verifying any test cases.")
        else:
            if observed.passed:
                result.passed.append(test)
            if observed.skipped:
                result.skipped.append(test)
    result.duration = context.budget.elapsed
    return result
