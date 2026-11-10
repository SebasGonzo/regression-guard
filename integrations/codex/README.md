# Codex integration

Run scripts/install_codex.ps1 -WhatIf from the checkout to preview a junction at ~/.agents/skills/regression-guard. The installer refuses an existing destination and never edits global settings. Remove -WhatIf only when installation is intended; restart Codex and invoke $regression-guard.

The optional lifecycle commands are the same shared backend:
- UserPromptSubmit: python "<checkout>/integrations/hooks/auto_check.py" --agent codex --phase start
- Stop: python "<checkout>/integrations/hooks/auto_check.py" --agent codex --phase stop

Use your exact checkout and Python paths. Preserve unrelated hooks and review/trust the definition in Codex. No global configuration is installed or rewritten by this change. Existing commands need no extra Node flag.

The start event supplies session_id/cwd. Stop compares the baseline and calls scripts/run.py check --mode targeted once, with timeout/compact reporting. Output uses the existing Codex decision/reason envelope to request reporting; a subsequent stop cannot rerun the same task.

Fixture tests validate the payload and CLI delegation. That is distinct from launching a real Codex session. See docs/installation-audit.md for observed installation paths and docs/validation.md for test scope.
