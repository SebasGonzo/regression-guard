# Installation audit — 2026-11-10

This is an observation of the current machine, not portable hardcoded engine configuration.

- Active source checkout: C:\DevTools\regression-guard. Started clean at 221e384142d903674ec05a8382ae6c5111a23cd3; work branch codex/multi-runner-regression.
- Codex skill junction: C:\Users\abgon\.agents\skills\regression-guard -> active checkout.
- Codex global hooks: C:\Users\abgon\.codex\hooks.json; UserPromptSubmit/Stop call the active integrations/hooks/auto_check.py with --agent codex. Trust entries are present in config.toml.
- Claude skill junction: C:\Users\abgon\.claude\skills\regression-guard -> active checkout.
- Claude global hook definitions: C:\Users\abgon\.claude\settings.json; command python plus args referencing the active shared hook and --agent claude. This audit did not launch a real Claude session.
- E:\Regression Guard is an earlier checkout at 5239ca8; it lacks the lifecycle hook. It was not updated.
- No Regression Guard hooks were found in the inspected Antigravity customization locations. Its installed builtin docs describe a camelCase lifecycle contract; the repository now provides an optional adapter/example. Skill discovery and actual automatic activation in Antigravity are not verified.
- No additional AGENTS.md was found in the active checkout or its inspected ancestors.

The prior implementation hardcoded pytest discovery/import analysis and had a Node CLI exception requiring both an exact node --test script and an option absent from the hook. The repair replaces that exception with the shared adapter registry.

No global configuration, alternate installation or consumer repository was edited. Linked skills intentionally see the active checkout's updated source/documentation.
