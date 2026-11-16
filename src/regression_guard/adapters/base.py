"""Common, file-based runner contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..git_analyzer import Change
from ..process import Budget
from ..project import matches
from ..test_runner import Run


@dataclass
class Policy:
    fallback: str = "unknown"
    max_tests: int = 50
    python_runner: str = "auto"


@dataclass
class Context:
    repo: Path
    changes: list[Change]
    files: list[str]
    mode: str
    policy: Policy
    budget: Budget
    execute: bool = False
    packages: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    @property
    def changed(self) -> set[str]:
        return {c.path for c in self.changes}


@dataclass
class Plan:
    runner: str
    directory: str = "."
    discovered: list[str] = field(default_factory=list)
    selected: list[str] = field(default_factory=list)
    reasons: dict[str, list[str]] = field(default_factory=dict)
    covered: set[str] = field(default_factory=set)
    limitations: list[str] = field(default_factory=list)
    unknown: bool = False
    available: bool = True
    metadata: dict = field(default_factory=dict)
    environment: dict = field(default_factory=lambda: {"kind": "host"})
    unavailable_reason: str | None = None

    @property
    def id(self) -> str:
        return f"{self.runner}@{self.directory}"


class Adapter(Protocol):
    name: str

    def detect(self, context: Context) -> list[Plan]: ...
    def prepare(self, context: Context, plan: Plan) -> None: ...
    def run(self, context: Context, plan: Plan) -> Run: ...


def configure_environment(context: Context, plan: Plan) -> None:
    profile = context.settings.get("environments", {}).get(plan.directory)
    if profile:
        plan.environment.update(profile)
    if plan.environment["kind"] != "host":
        plan.available = False
        plan.unavailable_reason = "environment_unavailable"
        plan.limitations.append(
            f"{plan.environment['kind']} profile requires an authorized external execution environment.")


def apply_mappings(context: Context, plan: Plan) -> None:
    for number, rule in enumerate(context.settings.get("mappings", []), 1):
        context.budget.check()
        paths = sorted(mapped_changes(context, rule))
        if paths:
            for test in plan.discovered:
                if matches(test, rule["tests"]):
                    plan.reasons.setdefault(test, []).extend(
                        f"mapping {number}: {path}" for path in paths)
                    plan.covered.update(paths)
    plan.selected = sorted(plan.reasons)


def mapped_changes(context: Context, rule: dict) -> set[str]:
    return {change.path for change in context.changes
            if matches(change.path, rule["changes"])
            or (change.old_path and matches(change.old_path, rule["changes"]))}


def apply_fallback(context: Context, plan: Plan, unresolved: set[str]) -> None:
    if not unresolved:
        return
    if (context.policy.fallback == "suite" and plan.discovered
            and len(plan.discovered) <= context.policy.max_tests):
        plan.selected = plan.discovered.copy()
        plan.covered.update(unresolved)
        for test in plan.selected:
            plan.reasons.setdefault(test, []).append("explicit suite fallback: impact could not be mapped")
        plan.limitations.append("Suite fallback explicitly requested; no dependency coverage is claimed.")
    else:
        plan.limitations.append("Unmapped changes: " + ", ".join(sorted(unresolved)))
        if context.policy.fallback == "suite" and len(plan.discovered) > context.policy.max_tests:
            plan.limitations.append("Suite fallback exceeds --max-tests; it was not scheduled.")
