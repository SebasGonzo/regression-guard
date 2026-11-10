---
name: regression-guard
description: Analyze Git changes and run bounded related regression checks through pytest, unittest, node:test, Vitest or Jest. Use for regression checks or before finalizing changes in an existing repository.
---

# Regression Guard

Before editing, inspect Git status, affected code, consumers and tests. Run `python <this skill directory>/scripts/run.py analyze --repo <repository>` to inspect the static plan. Quote paths with spaces. The engine lives in this linked checkout; do not copy it into the target repository.

After editing, inspect the actual diff. If an automatic Regression Guard Stop hook is active for this repository/task, let it perform the final TARGETED check once; otherwise run `python <this skill directory>/scripts/run.py check --repo <repository> --mode targeted --timeout 120`. FAST is an interim check. FULL and suite fallback require explicit user/project policy; never silently expand a hook selection to the entire suite.

The shared engine detects runners from configuration, scripts and conventions. It validates package-script aliases and invokes known runners with argument arrays; it never runs arbitrary npm scripts or installs dependencies. Missing/unsupported runners and unproven impact stay UNKNOWN. Do not bypass command policy to get a passing result.

Read [testing policy](references/testing_policy.md) before unfamiliar or risky suites and whenever the mapping is unknown. Review discovered, selected, executed, failed, skipped, pending, case counts, selection reasons, uncovered changes and limitations. Zero relevant cases cannot PASS. Passing selected tests does not prove absence of regressions.

Report failures as observed; establish whether they are new, preexisting or environmental before proposing fixes. Do not automatically repair or repeatedly rerun a lifecycle check.
