# Claude Code adapter

Personal skills load from `~/.claude/skills/regression-guard/SKILL.md`. The installer creates a junction to this source tree; invoke `/regression-guard` in a new Claude Code session. The engine is not copied.

Optional hook: merge `hooks.example.json` into a chosen Claude Code `settings.json` manually. It warns only when common global test/build files changed after an Edit or Write. It does not execute tests or block editing. Remove that `PostToolUse` entry to deactivate it. Adjust the absolute script path if the source tree is elsewhere. The installer never changes settings.

The global automatic integration uses `UserPromptSubmit` to capture a Git baseline and `Stop` to run TARGETED once if relevant code changed. It is separate from the optional edit-warning example. The hook feeds the result back to Claude for reporting and does not repair failures. See the root README for timeout and disable controls.

Reference: https://code.claude.com/docs/en/skills and https://code.claude.com/docs/en/hooks
