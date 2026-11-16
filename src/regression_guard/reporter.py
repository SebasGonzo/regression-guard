"""Report states are conservative about missing coverage."""
from __future__ import annotations

import json
from pathlib import Path

from .git_analyzer import Change, serialize
from .impact_analyzer import Impact
from .test_runner import Run
from .test_selector import Selection


def build(changes: list[Change], impact: Impact, selection: Selection, run: Run | None) -> dict:
    if run is None:
        state = "UNKNOWN" if impact.unknown or not selection.tests else "INCOMPLETE"
    elif run.failed:
        state = "FAIL"
    elif run.pending or run.skipped or run.timed_out:
        state = "INCOMPLETE"
    elif not selection.tests or impact.unknown:
        state = "UNKNOWN"
    else:
        state = "PASS"
    limits = sorted(set(selection.limitations + (["Passing tests do not prove absence of defects."] if run else [])))
    return {"status": state, "changes": serialize(changes), "risk": impact.risk,
            "dependents": impact.dependents, "selected": selection.tests,
            "executed": run.executed if run else [], "passed": run.passed if run else [],
            "failed": run.failed if run else [], "skipped": run.skipped if run else [],
            "pending": run.pending if run else selection.tests,
            "duration_seconds": run.duration if run else 0,
            "limitations": limits, "errors": run.errors if run else []}


def render(report: dict, *, compact: bool = False) -> str:
    lines = [f"Regression Guard: {report['status']} (risk: {report['risk']})"]
    if report.get("reasons"):
        lines.append("outcomes: " + ", ".join(report["reasons"]))
    if report.get("risk_assessed") is False:
        lines.append("change risk was not assessed")
    keys = ("changes", "dependents", "discovered", "selected", "executed", "passed", "failed", "skipped", "pending", "limitations", "errors")
    for key in keys:
        val = report.get(key, [])
        lines.append(f"{key}: {len(val) if isinstance(val, list) else val}")
        for item in (val[:4] if compact else val):
            lines.append(f"  - {item if isinstance(item, str) else item['source'] + ':' + item['status'] + ':' + item['path']}")
    if "runners" in report:
        runners = report["runners"]
        if compact:
            runners = sorted(runners, key=lambda r: not r["selected"])[:4]
        for runner in runners:
            lines.append(f"runner: {runner['id']} discovered={len(runner['discovered'])} selected={len(runner['selected'])} executed={len(runner['executed'])}")
            if runner["reasons"]:
                lines.append("  outcomes: " + ", ".join(runner["reasons"]))
            selections = list(runner["selection_reasons"].items())
            for test, reasons in (selections[:4] if compact else selections):
                lines.append(f"  {test}: " + "; ".join(reasons[:3] if compact else reasons))
        lines.append(f"case_counts: {report['case_counts']}")
    lines.append(f"duration_seconds: {report['duration_seconds']}")
    return "\n".join(lines)


def write_json(report: dict, path: Path) -> None:
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
