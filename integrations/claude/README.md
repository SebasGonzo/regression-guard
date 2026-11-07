# Claude Code integration

From the repository root on Windows, run `scripts/install_claude.ps1 -WhatIf` to preview a user-scoped junction at `~/.claude/skills/regression-guard`. Remove `-WhatIf` to install. Restart Claude Code and invoke `/regression-guard`. The installer preserves any existing destination and does not edit settings.

To add an optional edit warning, merge [hooks.example.json](hooks.example.json) into a chosen Claude Code settings file. It uses the installed Skill path and warns when common test/build configuration changed after Edit or Write. It does not run tests or block editing. Remove the `PostToolUse` entry to disable it.

For an optional automatic TARGETED check, configure `UserPromptSubmit` and `Stop` command Hooks to run `integrations/hooks/auto_check.py --agent claude --phase start` and `--phase stop`, respectively. Use the Python interpreter and Skill path on your machine. Review the command and allow a Stop timeout above the test budget. The installer does not configure these Hooks.

See the root README for limitations and disable controls. Official references: [Claude skills](https://code.claude.com/docs/en/skills) and [Claude Hooks](https://code.claude.com/docs/en/hooks).
