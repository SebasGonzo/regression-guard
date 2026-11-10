# Claude Code integration

Preview scripts/install_claude.ps1 -WhatIf to link ~/.claude/skills/regression-guard to this checkout. The installer refuses existing destinations and edits no global settings. Restart Claude Code and invoke /regression-guard after an intended installation.

The lifecycle backend is integrations/hooks/auto_check.py with --agent claude and --phase start (UserPromptSubmit) / stop (Stop). It consumes session_id/cwd and uses the same CLI, baseline, deduplication, timeout and runner policies as Codex. No separate selector is embedded here.

Command hooks can use command plus args for direct execution. Preserve existing settings; this repository does not activate or rewrite global hooks. The prior PostToolUse hooks.example.json remains an optional configuration warning and does not execute tests.

The existing additionalContext output envelope is retained. Contract tests call the real shared CLI in temporary repositories; they do not prove delivery to an actual Claude session.

[Claude hooks](https://code.claude.com/docs/en/hooks) documents command/args. Observed local configuration and verification limits are in docs/installation-audit.md.
