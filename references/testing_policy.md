# Testing policy

## Execution boundary

analyze/report read Git, configuration and source files; they never launch runners, import tests or evaluate JS config. check is permission to execute selected project test code and the installed runner's configuration, transforms/setup and dependencies. This tool is not a sandbox for those programs.

All runners use shell-free argument arrays. The engine requires Python 3.11+ and standard library; project pytest, Node, Vitest and Jest dependencies must already be installed. It never invokes npm/pnpm/yarn/npx to execute or fetch packages.

Package scripts are parsed and recursively resolved as data. Allowlisted endpoints are node --test, vitest [run], and jest, with local paths/patterns and narrowly supported configuration/run options. Shell syntax, arbitrary node entrypoints, eval/loaders, external paths, unknown flags, watch/update/allow-empty modes and recursive aliases are rejected. Direct invocation intentionally bypasses pretest/posttest and other package-manager lifecycle commands.

pytest keeps plugin autoload, bytecode and pytest cache disabled. Node uses TAP; framework runners use JSON summaries. Unrecognized/truncated summaries or zero verified cases cannot PASS. Skipped/deselected/expected-failure cases remain visible and prevent an unqualified PASS. Static discovery and selected-file counts are distinct from executed-case counts and code coverage.

## Selection and budget

TARGETED is the default; FAST keeps direct relationships. Explicit FULL selects discovered runner suites. Default fallback is UNKNOWN. --fallback suite (or explicit repository policy) permits a runner-suite expansion only within the configured file budget. It never suppresses known configuration/dependency uncertainty.

The single deadline includes Git, inventory, mapping, native discovery and execution. Default: 120 seconds and 50 files across runners. Timeout/file-budget exhaustion preserves pending work. On timeout the process group/tree is terminated; Windows taskkill or POSIX process-group cleanup has a short separate grace period. Detached processes outside that tree can escape cleanup.

Git inspection is read-only. The hook's initial snapshot is only an activation baseline, not an attribution system. Once triggered, the backend analyzes all current Git changes. Concurrent external edits and existing dirty files can influence selection. Hook state is kept in the system temporary directory, keyed by integration/session/repository.

## Honest states

- FAIL: selected test/file failure or failing test command.
- INCOMPLETE: analysis/execution timeout, pending file-budget work or known skipped/deselected cases.
- UNKNOWN: unsupported/missing runner, no relevant files or cases, unresolved dependency/configuration mapping, or unverifiable output.
- PASS: all selected relevant files completed, actual cases passed, with no known uncertainty or omissions. This is scoped evidence, never proof of zero regressions.

Failing tests take precedence; timeouts then take precedence over unknown strategy. Discovery/launch errors are reported and never automatically repaired.

## Supported limits

Python uses existing AST import/name mapping; static consumers can miss dynamic/indirect behavior. Supported pytest file configuration is testpaths/python_files/norecursedirs. Custom collectors, generated tests, plugins and case filters can require manual checks. unittest is inferred from TestCase suites or explicitly selected with python_runner.

JS/TS mapping is a conservative lexical graph of literal local imports, re-exports and require. Alias resolution, dynamic expressions, templates, escaped specifiers and ambiguous syntax can require manual review. It is not a compiler/type checker. Node's adapter supports native JS tests; it does not implicitly install TS/JSX loaders. Vitest/Jest discovery evaluates their real configuration only during check and may execute setup code. Their dependency mapping can remain UNKNOWN for complex projects even if selected tests pass.

Other ecosystems are not implicitly mapped to pytest or Node. Unsupported source changes keep coverage unknown.
