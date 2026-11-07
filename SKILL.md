---
name: regression-guard
description: Assess Git changes and run a bounded, related pytest selection after modifying an existing repository. Use for regression checks requested by the user or before finalizing code changes.
---

# Regression Guard

Before editing, inspect Git status, likely files, import consumers, and relevant tests. After editing, inspect the actual diff and run the shared CLI in `targeted` mode. Use `fast` only for an interim check. Use `full` only when the user requests it or project policy requires it.

Run `python <this skill directory>/scripts/run.py analyze --repo <repository>` before work. If an automatic Regression Guard Stop hook is active, let it perform the final TARGETED check once; otherwise run `python <this skill directory>/scripts/run.py check --repo <repository> --mode targeted --timeout 120` after work. Quote paths with spaces. The engine lives in this linked source tree; do not copy it into the target repository.

Review selected, pending, skipped, failed, and limitations in the report. A passing selection is evidence that those tests passed, not proof that the repository has no defects. If tests fail, identify whether the failure is new, preexisting, or environmental before changing code. Do not broaden edits without need. Never run a full suite automatically from a hook.

Read [testing policy](references/testing_policy.md) when the repository contains risky tests or the selection is unknown.
