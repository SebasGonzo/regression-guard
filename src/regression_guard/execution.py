"""Account for actual runner results, including zero cases and partial execution."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from .process import ProcessResult, invoke
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
        if result.total == 1 and re.search(r"(?m)^# Subtest: .*\.(?:mjs|cjs|js)\s*$", output) and not result.failed:
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
    summaries = re.findall(r"(?m)^=*\s*(\d+[^\r\n]* in [\d.]+s)\s*=*\s*$", output)
    summary = summaries[-1] if summaries else ""
    def pytest_number(label):
        found = re.search(r"\b(\d+) " + label + r"\b", summary)
        return int(found.group(1)) if found else 0
    passed, failed, skipped = (pytest_number(x) for x in ("passed", "failed", "skipped"))
    skipped += sum(pytest_number(x) for x in ("deselected", "xfailed", "xpassed"))
    return Counts(passed + failed + skipped, passed, failed, skipped)


def observe(process: ProcessResult, runner: str) -> tuple[Counts, str]:
    output, code = process.output, process.code
    if process.error:
        return Counts(), "infrastructure_error"
    try:
        observed = counts(output, runner)
    except (ValueError, TypeError, KeyError):
        return Counts(), "insufficient_evidence"
    if observed.total != observed.passed + observed.failed + observed.skipped:
        return Counts(), "insufficient_evidence"
    missing = re.search(r"ModuleNotFoundError:|ERR_MODULE_NOT_FOUND|Cannot find module", output)
    collection = (
        (runner == "pytest" and bool(re.search(r"ERROR collecting|errors? during collection", output)))
        or (runner == "unittest" and "unittest.loader._FailedTest" in output)
        or (runner == "node:test" and bool(re.search(
            r"(?m)^not ok \d+ - .*\.(?:mjs|cjs|js)\s*$", output))
            and bool(re.search(r"(?m)^  failureType: 'testCodeFailure'", output)))
    )
    # Node reports an uncaught file-level failure as a TAP test wrapper.
    if collection and runner in {"node:test", "unittest"}:
        if observed.failed:
            observed.failed -= 1
            observed.total -= 1
    if observed.failed:
        return observed, "test_failure"
    if code and (collection or (runner in {"vitest", "jest"} and not observed.total and missing)):
        return observed, "environment_unavailable" if missing else "collection_error"
    if runner == "pytest" and code and re.search(r"No module named pytest\b", output):
        return observed, "environment_unavailable"
    if code and not (runner == "pytest" and code == 5):
        if runner in {"vitest", "jest"} and re.search(r'"numRuntimeErrorTestSuites"\s*:\s*[1-9]', output):
            return observed, "collection_error"
        return observed, "infrastructure_error"
    if observed.skipped:
        return observed, "cases_skipped"
    if not observed.total:
        return observed, "insufficient_evidence"
    return observed, "passed"


def execute_files(context, plan, command: Callable[[str], list[str]]) -> Run:
    result = Run(pending=plan.selected.copy())
    for test in plan.selected:
        if len(result.executed) >= context.policy.max_tests or context.budget.remaining <= 0:
            result.timed_out = context.budget.remaining <= 0
            result.budget_exhausted = True
            result.errors.append("Total time or file budget exhausted; remaining files were not executed.")
            break
        argv = command(test)
        result.commands.append(argv)
        process = invoke(argv, context.repo / plan.directory, context.budget)
        if process.timed_out:
            result.timed_out = True
            result.budget_exhausted = True
            result.outcomes[test] = "budget_exhausted"
            result.errors.append(f"Timeout while running {plan.runner}: {test}")
            break
        if process.code is None:
            result.outcomes[test] = "infrastructure_error"
            result.errors.append(f"{test}: {process.error or 'runner unavailable'}")
            break
        result.pending.remove(test)
        result.executed.append(test)
        observed, outcome = observe(process, plan.runner)
        result.outcomes[test] = outcome
        for key in ("total", "passed", "failed", "skipped"):
            result.case_counts[key] += getattr(observed, key)
        if outcome == "test_failure":
            result.failed.append(test)
        if outcome not in {"passed", "cases_skipped"}:
            detail = process.error or process.output[-3500:].strip()
            result.errors.append(f"{test}: {outcome}" + (f"\n{detail}" if detail else ""))
        if observed.passed and outcome in {"passed", "cases_skipped"}:
            result.passed.append(test)
        if observed.skipped:
            result.skipped.append(test)
    result.duration = context.budget.elapsed
    return result
