# Antigravity integration: optional and not activated

No installed Regression Guard lifecycle hook was found during the local audit. This change supplies a payload adapter and hooks.example.json inside the repository; it does not create global skills, hooks or settings and does not claim a live IDE validation.

The installed product's local lifecycle documentation describes named hooks with flat PreInvocation/Stop arrays and camelCase payloads. The adapter consumes conversationId and exactly one workspacePaths entry. It records a baseline on PreInvocation with invocationNum=1 only; repeated invocations must not overwrite it. Stop calls the same scripts/run.py CLI once and returns decision=continue with the report; the claim suppresses further runs.

Before manual installation:
1. Confirm your product version sends this initial invocation number, conversation ID and workspace contract. Multiple-workspace events are intentionally unsupported.
2. Replace <checkout> in hooks.example.json with the actual checkout path and set the appropriate Python executable.
3. Merge the example into the correct product customization root, preserving other hooks. Review/trust it according to that product.
4. Validate first in a disposable Git repository with an initial commit: baseline, one code edit, one Stop result and no duplicate execution.

A contract test simulates these payloads and exercises the real shared backend. Actual Antigravity lifecycle behavior remains unverified. If your version differs, run the CLI directly as documented in integrations/generic/README.md rather than inventing a hook contract.
