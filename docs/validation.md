# Validation — 2026-11-10

Local version 1.1.0, branch codex/multi-runner-regression. Base commit: 221e384142d903674ec05a8382ae6c5111a23cd3. Changes remain uncommitted; no release or remote update was performed.

## Final verification

Python 3.11.9; pytest 9.1.1; Node v22.22.0. Real project-local framework fixtures used Vitest 3.2.4 and Jest 30.2.0. Their dependencies were installed only in a dedicated temporary directory with npm --ignore-scripts --no-audit --no-fund, not in Regression Guard or a consumer.

Command run from the active checkout (REGRESSION_GUARD_REAL_JS_ROOT pointed to that dedicated fixture):

~~~powershell
python -B scripts/run.py check --repo . --mode targeted --fallback suite --max-tests 50 --timeout 120 --json docs/self-check.json --compact
~~~

Actual result: UNKNOWN (CLI exit 3); five files discovered, selected, executed and passed. 48 cases passed, zero failed/skipped/pending; 74.235 seconds.

| Test file | Final passed cases | Evidence |
| --- | ---: | --- |
| tests/test_acceptance.py | 5 | Original pytest/Git selection, regression, timeout and unknown behavior |
| tests/test_adapters.py | 32 | Five runner contracts; real Python/Node and simulated framework variants; detection/configuration/aliases, direct/transitive changes, failure/timeout/no cases, absent/incompatible runners, mixed projects, budgets, script protection, fake imports and preserved legacy selection |
| tests/test_hooks.py | 3 | Original once-only, preexisting-dirt and no-tests hook tests |
| tests/test_integrations.py | 6 | Codex/Claude/Antigravity/generic payload adapters call the real common CLI; baseline commits, continuation, disable and malformed inputs |
| tests/test_real_javascript.py | 2 | Actual Vitest/Jest discovery, related selection, success and deliberate failure; selected filenames include spaces |

Framework timeouts, missing/unsupported runners and malformed output are additionally covered by simulated contract fixtures. Real framework validation covers the specific versions above, not arbitrary versions/configurations. No actual Codex/Claude/Antigravity client session was launched as part of this implementation.

The global UNKNOWN was not hidden. Remaining limitations reported by the backend:

- Coverage not established for changed paths: integrations/antigravity/hooks.example.json
- Global test/build configuration changed; selective coverage may be insufficient.
- Passing selected tests does not prove absence of defects.
- Suite fallback explicitly requested; no dependency coverage is claimed.

The configured suite fallback was explicit, scoped to Regression Guard and bounded to five files within 120 seconds. It did not suppress configuration uncertainty. No consumer project tests were run.

The generated [self-check JSON](self-check.json) contains actual commands, selection reasons, covered/uncovered paths and case/file counts. It is an ignored local artifact so generating it does not become a subsequent source change.

Implementation-stage runs also passed: the eight original tests; 24 initial adapter tests; six lifecycle tests; two real-framework tests; a 45-test consolidated suite; four focused detection tests. An earlier self-check ran 47 passing cases and also correctly returned UNKNOWN before the final malformed-output regression was added.

Static syntax parsing and git diff --check completed successfully. The obsolete E: checkout stayed clean. No global settings, alternate installation or consumer repository was edited. The dedicated real-runner temporary fixture was removed after validation.

## Installation status

Codex and Claude skill junctions and hook definitions already reference the active checkout. Their configured paths remain in place. No reinstall or global configuration edit was performed. Automatic delivery in real clients was not retested. Antigravity requires manual integration and live validation; see [its instructions](../integrations/antigravity/README.md). The generic CLI works independently of the editor.

## Files changed or added

- C:/DevTools/regression-guard/.gitignore
- C:/DevTools/regression-guard/README.md
- C:/DevTools/regression-guard/SKILL.md
- C:/DevTools/regression-guard/docs/installation-audit.md
- C:/DevTools/regression-guard/docs/validation.md
- C:/DevTools/regression-guard/integrations/antigravity/README.md
- C:/DevTools/regression-guard/integrations/antigravity/hooks.example.json
- C:/DevTools/regression-guard/integrations/claude/README.md
- C:/DevTools/regression-guard/integrations/codex/README.md
- C:/DevTools/regression-guard/integrations/generic/README.md
- C:/DevTools/regression-guard/integrations/hooks/auto_check.py
- C:/DevTools/regression-guard/pyproject.toml
- C:/DevTools/regression-guard/references/testing_policy.md
- C:/DevTools/regression-guard/scripts/run.py
- C:/DevTools/regression-guard/src/regression_guard/__init__.py
- C:/DevTools/regression-guard/src/regression_guard/adapters/__init__.py
- C:/DevTools/regression-guard/src/regression_guard/adapters/base.py
- C:/DevTools/regression-guard/src/regression_guard/adapters/javascript.py
- C:/DevTools/regression-guard/src/regression_guard/adapters/python.py
- C:/DevTools/regression-guard/src/regression_guard/cli.py
- C:/DevTools/regression-guard/src/regression_guard/dependencies.py
- C:/DevTools/regression-guard/src/regression_guard/engine.py
- C:/DevTools/regression-guard/src/regression_guard/execution.py
- C:/DevTools/regression-guard/src/regression_guard/git_analyzer.py
- C:/DevTools/regression-guard/src/regression_guard/impact_analyzer.py
- C:/DevTools/regression-guard/src/regression_guard/process.py
- C:/DevTools/regression-guard/src/regression_guard/project.py
- C:/DevTools/regression-guard/src/regression_guard/reporter.py
- C:/DevTools/regression-guard/src/regression_guard/scripts.py
- C:/DevTools/regression-guard/src/regression_guard/test_runner.py
- C:/DevTools/regression-guard/src/regression_guard/test_selector.py
- C:/DevTools/regression-guard/tests/helpers.py
- C:/DevTools/regression-guard/tests/test_adapters.py
- C:/DevTools/regression-guard/tests/test_integrations.py
- C:/DevTools/regression-guard/tests/test_real_javascript.py
