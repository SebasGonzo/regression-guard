"""One editor-independent backend for every CLI and hook integration."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .adapters import ADAPTERS, Context, Policy
from .git_analyzer import changes, root, serialize
from .process import Budget, BudgetExceeded
from .project import CONFIG_NAMES, inventory, packages, policy_config, relevant
from .test_runner import Run


def deduplicate(plans) -> None:
    owners = {}
    by_priority = sorted(plans, key=lambda plan: (
        -len(Path(plan.directory).parts), plan.metadata.get("script") == "conventions"))
    for plan in by_priority:
        retained = []
        for test in plan.selected:
            first = owners.setdefault(test, plan)
            if first is plan:
                retained.append(test)
                continue
            plan.metadata.setdefault("duplicates", {})[test] = first.id
            first.reasons[test] = sorted(set(first.reasons[test] + plan.reasons[test]))
            if (first.runner, first.metadata.get("options")) != (plan.runner, plan.metadata.get("options")):
                first.unknown = True
                first.limitations.append(f"Overlapping runner configurations for {test}; selected {first.id}.")
        plan.selected = retained
        plan.reasons = {test: plan.reasons[test] for test in retained}


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
                      js_packages, problems, settings)
    planned = [(adapter, plan) for adapter in ADAPTERS for plan in adapter.detect(context)]
    for adapter, plan in planned:
        adapter.prepare(context, plan)
    deduplicate([plan for _, plan in planned])
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
        reasons = set(run.outcomes.values())
        if run.unknown:
            reasons.add("insufficient_evidence")
        if run.budget_exhausted:
            reasons.add("budget_exhausted")
        if plan.unavailable_reason and (plan.selected or plan.metadata.get("discovery_commands")):
            reasons.add(plan.unavailable_reason)
        if not plan.selected:
            reasons.add("no_tests_selected")
        elif plan.unknown:
            reasons.add("insufficient_evidence")
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
            "script": plan.metadata.get("script"),
            "environment": plan.environment, "reasons": sorted(reasons),
            "outcomes": run.outcomes, "duplicate_tests": plan.metadata.get("duplicates", {}),
        })
    def union(key):
        return sorted({p for report in reports for p in report[key]})
    covered = {p for _, plan in planned for p in plan.covered}
    mappings = settings.get("mappings", [])
    required = {c.path for c in items if relevant(c.path, mappings)
                or (c.old_path and relevant(c.old_path, mappings))}
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
    reasons = {reason for report in reports for reason in report["reasons"]
               if reason != "no_tests_selected"}
    if not selected:
        reasons.add("no_tests_selected")
    if uncovered or context.limitations or not planned:
        reasons.add("insufficient_evidence")
    unknown = reasons & {"no_tests_selected", "insufficient_evidence", "collection_error",
                         "infrastructure_error", "environment_unavailable"}
    if failed:
        status = "FAIL"
    elif "budget_exhausted" in reasons:
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
    risky_configuration = any(Path(path).name in CONFIG_NAMES for path in required)
    return {"status": status, "risk": "high" if risky_configuration else "medium" if dependents else "low",
            "reasons": sorted(reasons), "risk_assessed": bool(required),
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
            "status": "INCOMPLETE", "risk": "low", "risk_assessed": False,
            "reasons": ["budget_exhausted"], "changes": [], "dependents": [],
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
