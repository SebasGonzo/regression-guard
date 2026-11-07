# OpenAI Codex integration

From the repository root on Windows, run `scripts/install_codex.ps1 -WhatIf` to preview a user-scoped junction at `~/.agents/skills/regression-guard`. Remove `-WhatIf` to install. Restart Codex and invoke `$regression-guard`. The installer preserves any existing destination and does not edit settings or Hooks.

For an optional automatic TARGETED check, configure `UserPromptSubmit` and `Stop` command Hooks to run `integrations/hooks/auto_check.py --agent codex --phase start` and `--phase stop`, respectively. Use the Python interpreter and Skill path on your machine. Review and trust the exact Hook definition before enabling it. Allow a Stop timeout above the test budget. No Hook is installed by this repository.

See the root README for limitations and disable controls. Official references: [Skill installation](https://developers.openai.com/api/reference/cli) and [Hooks](https://developers.openai.com/docs/hooks).
