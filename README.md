# Regression Guard 1.1

Regression Guard reads Git changes, discovers configured test runners and executes a bounded selection of related test files. Every editor uses the same Python CLI and backend. The engine requires Python 3.11+ and Git; install each project's test dependencies separately.

## Quick start

```powershell
python scripts/run.py analyze --repo 'C:\path with spaces\project'
python scripts/run.py check --repo 'C:\path with spaces\project' --mode targeted --timeout 120
python scripts/run.py report --repo 'C:\path with spaces\project' --json report.json
```

`analyze` and `report` inspect static files and Git; they never launch a test runner or evaluate JavaScript configuration. For Vitest/Jest their discovery is provisional until `check` queries the installed runner.

No account, API key, global npm package or engine runtime dependency is required. pytest must be installed in the Python interpreter running Regression Guard. Node must be on PATH; Vitest/Jest must be installed in the analyzed package's local node_modules. The engine never downloads dependencies.

## Runner support

| Runner | Detection and discovery | Selection / execution |
| --- | --- | --- |
| pytest | pytest.ini, pyproject.toml, tox.ini, setup.cfg; python_files, testpaths, norecursedirs; default test_*.py / *_test.py | Existing Python AST import/name selection; same interpreter, per-file pytest, plugin autoload/cache/bytecode disabled |
| unittest | Standard-library TestCase classes in conventional Python test files; explicit python_runner override | Shared Python selection; unittest discover scoped to one selected filename |
| node:test | Allowlisted package scripts or node:test imports; explicit patterns including braces and recursive globs; native JS conventions otherwise | Local static imports/re-exports/require, transitive in TARGETED; node --test with explicit files and TAP output |
| Vitest | Allowlisted scripts, vitest.config files or test imports; native list --filesOnly --json during check | Local static dependency selection; native discovery honors project configuration; local Vitest CLI, run mode and one worker |
| Jest | Allowlisted scripts, Jest config/package field or @jest/globals imports; native --listTests --json during check | Local static dependency selection; local Jest CLI, --runTestsByPath and --runInBand |

Package roots are discovered recursively, excluding dependency/build/environment directories. packageManager and npm/pnpm/yarn lockfiles are reported. Configured scripts and test imports decide the runner; React/Vite alone does not imply a test runner. Test patterns and local binary paths are package-relative. Dependency links resolving outside the analyzed Git root are unsupported.

Python auto mode prefers pytest when pytest configuration or function-style tests exist; an exclusively unittest-style conventional suite uses unittest. Override ambiguities with --python-runner or repository policy. pytest function/class collection customizations beyond the supported file options remain the runner's responsibility.

JavaScript mapping supports literal relative imports, re-exports and require calls. It is deliberately conservative about aliases, nonliteral imports, template expressions, ambiguous lexical syntax, unresolved/deleted modules and TypeScript-only imports. Unsupported resolution stays UNKNOWN. It is not a full JS/TS parser or coverage instrument. Node does not implicitly install TS/JSX loaders. Vitest/Jest can use their installed transforms, but complex alias-based impact mapping may remain UNKNOWN.

## Modes and coverage policy

- FAST selects direct relationships.
- TARGETED adds statically recognized consumers/transitive JS relationships.
- FULL is explicit and selects all discovered files of detected runners.
- Default fallback is UNKNOWN. No full-suite fallback occurs implicitly.
- --fallback suite explicitly permits expanding an unmapped selection to that runner's discovered suite, only when it fits --max-tests. Mapping/configuration limitations can still keep the result UNKNOWN.

```powershell
python scripts/run.py check --repo 'C:\project' --fallback suite --max-tests 20 --timeout 30
```

The default global file budget is 50. All runners share one wall-clock deadline for Git inspection, inventory, mapping, native discovery and test execution. Process-tree cleanup after timeout has a separate short grace period. When time or file budget ends, unfinished selections are pending; they do not pass.

Optional .regression-guard.toml, or [tool.regression_guard] in pyproject.toml:

```toml
fallback = "unknown"
max_tests = 50
python_runner = "auto" # auto | pytest | unittest
```

CLI flags override repository policy. Unknown policy keys and invalid values are rejected.

## Script allowlist

Scripts are data, never shell commands. The resolver accepts:

- node --test followed by relative test paths/patterns.
- vitest / vitest run, and jest.
- --config / -c with a local relative configuration file; non-watch run/CI flags.
- Local aliases through npm test, npm run NAME, pnpm [run] NAME, yarn [run] NAME, including validated forwarded arguments.

Shell operators, substitutions, environment assignments, npx/exec/downloads, arbitrary node scripts, loaders/eval/require flags, external paths, watch/update/zero-test-success flags and unrecognized options are rejected. Cycles are rejected. A rejected primary test script is reported as a verification limitation. Auxiliary arbitrary scripts are not automatically run. Recognized independent test:* scripts can contribute additional runners.

Execution uses argument arrays and shell=False. It calls Node and known project-local CLI entrypoints directly, not npm/pnpm/yarn shims or lifecycle scripts. pretest/posttest hooks are therefore not executed. The historical --allow-node-test flag is accepted for compatibility but is no longer required for validated targeted Node checks.

## Result contract

| State | Meaning |
| --- | --- |
| PASS | Selected relevant files finished successfully, at least one test case passed, and no known mapping/runner uncertainty or omitted cases remain |
| FAIL | A selected runner reports a failed test/file or a failing test-process exit |
| INCOMPLETE | Analysis/execution timed out, the global file budget left pending work, or known cases were skipped/deselected |
| UNKNOWN | No relevant tests/cases, unsupported or missing runner, unresolved impact/configuration, or unusable output prevents a coverage claim |

FAIL takes precedence over timeout/uncertainty; timeout takes precedence over UNKNOWN. JSON includes discovered/selected/executed/passed/failed/skipped/pending files, per-runner reasons, commands, covered/uncovered changes, case counts, limitations and errors. Aggregate file lists deduplicate paths; per-runner reports preserve separate executions. Counts measure reported cases and files, not code coverage. PASS never proves absence of regressions.

Exit codes: 0 PASS, 1 FAIL, 2 INCOMPLETE, 3 UNKNOWN, 4 input/configuration/Git error.

## Editor integrations

- [Codex](integrations/codex/README.md): optional skill junction and UserPromptSubmit/Stop hooks.
- [Claude Code](integrations/claude/README.md): optional skill junction and the same lifecycle backend.
- [Antigravity](integrations/antigravity/README.md): payload adapter and manual example; not automatically installed or claimed verified in the IDE.
- [Other editors](integrations/generic/README.md): direct CLI or explicit start/stop JSON wrapper.

The Windows skill installers preserve existing destinations and do not change global settings or enable hooks. Preview with scripts/install_codex.ps1 -WhatIf or scripts/install_claude.ps1 -WhatIf.

Lifecycle hooks keep the baseline, once-per-task claim, configurable 1–150 second budget (default 120), recursion guard and disable controls. Set REGRESSION_GUARD_DISABLE=1 or create ~/.regression-guard.disabled to pause. State lives in the system temporary directory. The baseline decides whether to trigger; the backend then reads the repository's current Git diff, including existing dirty files. Concurrent edits cannot reliably be attributed to a person/editor.

## Safety

[Testing policy](references/testing_policy.md) defines execution boundaries. Running tests or runner configuration is executing project code: it can write files, use credentials, call services and spawn processes. Command validation is not an operating-system sandbox. Inspect unfamiliar repositories or use a disposable environment. No automatic repairs occur.

## Development verification

```powershell
$env:PYTHONPATH = 'src'
python -B -m unittest discover -s tests -v
```

The default suite uses temporary Git repositories, actual pytest/unittest/Node and simulated Vitest/Jest contract binaries. Optional real-framework checks are in tests/test_real_javascript.py. Set REGRESSION_GUARD_REAL_JS_ROOT to a dedicated temporary directory named regression-guard-real-runners-* with project-local vitest@3.2.4 and jest@30.2.0 installed using --ignore-scripts. This opt-in harness initializes its own Git fixture and writes test files there; never point it at a consumer repository. The tests do not install packages.

See [validation evidence](docs/validation.md) and [installation audit](docs/installation-audit.md).

Runner references: [Node 22 test runner](https://nodejs.org/docs/latest-v22.x/api/test.html), [Vitest CLI](https://vitest.dev/guide/cli), [Jest CLI](https://jestjs.io/docs/cli), [npm lifecycle scripts](https://docs.npmjs.com/cli/v11/using-npm/scripts/).

## Extending

Implement the Adapter protocol in src/regression_guard/adapters/base.py, add it to ADAPTERS, and return the common Plan/Run types. Keep detection, discovery, selection and execution inside the adapter/backend; lifecycle hooks must never implement runner-specific selection. Add isolated fixtures for discovery, selection, success/failure, no cases, missing runner, timeouts, command policy and mixed projects. Unsupported ecosystems remain UNKNOWN.

MIT license; see LICENSE.
