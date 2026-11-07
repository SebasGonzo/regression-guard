# Regression Guard 1.0

Local Git change analysis and bounded pytest checks for Python repositories. Requires Windows 10/11, PowerShell, Git, Python 3.11+, and pytest for `check`. The CLI itself has no runtime dependencies.

## Run from source

```powershell
python scripts/run.py analyze --repo 'C:\My Project'
python scripts/run.py check --repo 'C:\My Project' --mode targeted --timeout 120 --json report.json
python scripts/run.py check --repo 'C:\My Project' --mode fast
python scripts/run.py check --repo 'C:\My Project' --mode full
python scripts/run.py check --repo 'C:\My Node Project' --allow-node-test --timeout 120
python scripts/run.py report --repo 'C:\My Project' --base HEAD~1
python scripts/run.py --help
```

`analyze` and `report` are read-only plans; `check` runs pytest. `--base` compares that commit to HEAD in addition to staged, unstaged, and untracked changes. `fast` chooses direct tests; `targeted` also chooses tests of identified import consumers; `full` chooses all discovered pytest files. `full` is never implicit. A test file counts as passed only if pytest returns success; individual test case counts are not currently reported.

Exit codes: 0 PASS, 1 FAIL, 2 INCOMPLETE, 3 UNKNOWN, 4 input/Git error. The JSON report has the same status and lists changed paths, risk, dependents, selected/executed/passed/failed/skipped/pending files, duration, errors, and limitations.

## Installation (manual action, not run by this project)

Review the source and run `scripts/install_codex.ps1 -WhatIf` or `scripts/install_claude.ps1 -WhatIf`. Remove `-WhatIf` to install after authorization. Both scripts require Python 3.11+, refuse an existing destination, and create a junction to this source checkout. No package or dependency is installed. Updating the source checkout updates both linked Skills. Use `-Uninstall` for a safe uninstall; it only removes a junction targeting this checkout. See each integration README for invocation and optional Claude hook setup.

## Safety and limits

Git commands are read-only and use NUL-delimited paths. `check` does not install dependencies or modify virtual environments. It disables pytest cache, bytecode writes, and third-party pytest plugin autoload. **Test code can still have side effects.** Inspect unfamiliar tests and use a disposable checkout for untrusted repositories. The timeout applies to direct test processes; subprocesses spawned by tests may survive it. Python import mapping is static and conservative. Dynamic imports, indirect dependencies, generated tests, integration tests without recognizable names, and JS/TS mapping need manual review. `package.json` test scripts are detected but only the exact `node --test` script can run, with `--allow-node-test`; other scripts are never executed. Passing selected tests never proves the absence of all regressions.

## Validation

`$env:PYTHONPATH='src'; python -m unittest discover -s tests -v` runs isolated Git fixtures in temporary directories, including passing and failing checks, shared module selection, no tests, untracked/renamed/staged/unstaged files, timeout, and paths with spaces. It does not touch other projects.
