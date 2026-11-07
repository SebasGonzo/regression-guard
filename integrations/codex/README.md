# Codex adapter

The user-scoped skill directory is `~/.agents/skills/regression-guard` according to current OpenAI CLI installation documentation. The installer creates a junction to this source tree. Restart Codex and invoke `$regression-guard`. No Claude style hook is installed for Codex.

The separate global Hook uses `UserPromptSubmit` and `Stop`. Codex requires review and trust of its exact Hook definition in `/hooks`; until trusted, Codex skips it. The result is fed back once for reporting. See the root README for timeout and disable controls.

Reference: https://developers.openai.com/api/reference/cli
