"""One editor-independent backend for every CLI and hook integration."""
from __future__ import annotations

from dataclasses import asdict

from .adapters import ADAPTERS, Context, Policy
from .git_analyzer import changes, root, serialize
from .process import Budget, BudgetExceeded
from .project import inventory, packages, policy_config, relevant
from .test_runner import Run


def _inspect(repo, *, mode="targeted", base=None, execute=False, timeout=120,
            fallback=None, max_tests=None, python_runner=None, _budget=None) -> dict:
    budget = _budget or Budget(timeout)
    repo = root(repo, budget)
    items = changes(repo, base, budget)
    settings = policy_config(repo)
    policy = Policy(fallback or settings.get("fallback", "unknown"),
                    max_tests if max_tests is not None else settings.get("max_tests", 50),
                    python_runner or settings.get("python_runner", "auto"))
    if policy.fallback not in {"unknown", "suite"}:
        raise ValueError("fallback must be unknown or suite.")
    if not isinstance(policy.max_tests, int) or isinstance(policy.max_tests, bool) or policy.max_tests < 1:
        raise ValueError("max_tests must be a positive integer.")
    if policy.python_runner not in {"auto", "pytest", "unittest"}:
        raise ValueError("python_runner must be auto, pytest or unittest.")
    files = inventory(repo, budget)
    js_packages, problems = packages(repo, files)
    context = Context(repo, items, files, mode, policy, budget, execute,
                      js_packages, problems)
    planned = [(adapter, plan) for adapter in ADAPTERS for plan in adapter.detect(context)]
    for adapter, plan in planned:
        adapter.prepare(context, plan)
    reports, runs = [], []
    executed_files = 0
    file_budget = policy.max_tests
    for adapter, plan in planned:
        run = None
        if execute and plan.selected and plan.available:
            policy.max_tests = max(0, file_budget - executed_files)
            run = adapter.run(context, plan)
            executed_files += len(run.executed)
        if run is None:
            run = Run(pending=plan.selected.copy())
        policy.max_tests = file_budget
        runs.append(run)
        reports.append({
            "id": plan.id, "runner": plan.runner, "directory": plan.directory,
            "available": plan.available, "discovered": plan.discovered,
            "selected": plan.selected, "selection_reasons": plan.reasons,
            "covered_changes": sorted(plan.covered), "limitations": sorted(set(plan.limitations + run.unknown)),
            "mapping_unknown": plan.unknown, "executed": run.executed, "passed": run.passed,
            "failed": run.failed, "skipped": run.skipped, "pending": run.pending,
            "case_counts": run.case_counts, "commands": run.commands,
            "discovery_commands": plan.metadata.get("discovery_commands", []),
            "package_manager": plan.metadata.get("package_manager"),
        })
    def union(key):
        return sorted({p for report in reports for p in report[key]})
    covered = {p for _, plan in planned for p in plan.covered}
    required = {c.path for c in items if relevant(c.path)}
    uncovered = sorted(required - covered)
    limitations = context.limitations.copy()
    limitations.extend(x for report in reports for x in report["limitations"])
    if uncovered:
        limitations.append("Coverage not established for changed paths: " + ", ".join(uncovered))
    if not items:
        limitations.append("No changes detected.")
    if not planned:
        limitations.append("No supported test runner detected.")
    selected, failed = union("selected"), union("failed")
    timed_out = any(r.timed_out for r in runs) or any(
        plan.metadata.get("timed_out") for _, plan in planned)
    unknown = (bool(context.limitations) or bool(uncovered) or not selected
               or any(plan.unknown or not plan.available for _, plan in planned)
               or any(run.unknown for run in runs))
    if failed:
        status = "FAIL"
    elif timed_out:
        status = "INCOMPLETE"
    elif unknown:
        status = "UNKNOWN"
    elif not execute or union("pending") or union("skipped"):
        status = "INCOMPLETE"
    elif not any(run.case_counts["passed"] for run in runs):
        status = "UNKNOWN"
    else:
        status = "PASS"
    if execute and selected:
        limitations.append("Passing selected tests does not prove absence of defects.")
    case_counts = {k: sum(run.case_counts[k] for run in runs)
                   for k in ("total", "passed", "failed", "skipped")}
    dependents = sorted({p for _, plan in planned for p in plan.metadata.get("dependents", [])})
    return {"status": status, "risk": "high" if unknown else "medium" if dependents else "low",
            "changes": serialize(items), "dependents": dependents, "discovered": union("discovered"),
            "selected": selected, "executed": union("executed"), "passed": union("passed"),
            "failed": failed, "skipped": union("skipped"), "pending": union("pending"),
            "uncovered_changes": uncovered, "duration_seconds": budget.elapsed,
            "case_counts": case_counts, "policy": asdict(policy), "runners": reports,
            "limitations": sorted(set(limitations)),
            "errors": [error for run in runs for error in run.errors]}

def inspect(repo, **kwargs) -> dict:
    budget = Budget(kwargs.get("timeout", 120))
    try:
        return _inspect(repo, **kwargs, _budget=budget)
    except BudgetExceeded as exc:
        return {
            "status": "INCOMPLETE", "risk": "high", "changes": [], "dependents": [],
            "discovered": [], "selected": [], "executed": [], "passed": [], "failed": [],
            "skipped": [], "pending": [], "uncovered_changes": [],
            "duration_seconds": budget.elapsed,
            "case_counts": dict(total=0, passed=0, failed=0, skipped=0),
            "policy": {"fallback": kwargs.get("fallback") or "unknown",
                       "max_tests": kwargs.get("max_tests") or 50,
                       "python_runner": kwargs.get("python_runner") or "auto"},
            "runners": [], "limitations": [str(exc), "Analysis did not finish; no coverage is established."],
            "errors": [str(exc)],
        }
