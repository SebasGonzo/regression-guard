# Regression Guard 1.0

Regression Guard analyzes local Git changes and runs a bounded selection of related tests. It is a reusable Python Skill for Claude Code and OpenAI Codex on Windows. FULL is never selected implicitly.

## Requirements

- Windows 10/11, PowerShell, Git, and Python 3.11+.
- pytest in the Python environment used for checks. Analysis requires only the Python standard library.
- A Git repository to analyze, with its own test dependencies installed separately.

No GitHub account or API key is needed to use the tool.

## Quick start

Clone this repository and run from its root:

```powershell
python scripts/run.py analyze --repo 'C:\path\to\your-repo'
python scripts/run.py check --repo 'C:\path\to\your-repo' --mode targeted --timeout 120
python scripts/run.py report --repo 'C:\path\to\your-repo' --base HEAD~1
```

`analyze` and `report` do not run tests. `check` runs selected tests. Add `--json report.json` for a machine-readable report. `--base` compares a commit with HEAD, alongside staged, unstaged, and untracked changes.

| Mode | Selection | Purpose |
| --- | --- | --- |
| FAST | Directly related tests | Interim feedback. |
| TARGETED | Direct tests and tests of statically identified Python import consumers | Default final check. |
| FULL | All discovered pytest files | Explicit broad check only. |

```powershell
python scripts/run.py check --repo 'C:\path\to\your-repo' --mode fast
python scripts/run.py check --repo 'C:\path\to\your-repo' --mode full --timeout 120
```

The total timeout defaults to 120 seconds. Exit codes: 0 PASS, 1 FAIL, 2 INCOMPLETE, 3 UNKNOWN, 4 input/Git error. Reports include changed paths, risk, dependents, selected/executed/passed/failed/skipped/pending test files, errors, and limitations. A passed *file* means pytest succeeded for that file; individual test case counts are not reported.

## Install as a Skill

The Windows installers create a junction to this checkout. They refuse an existing destination, install no Python packages, and do not edit agent settings or Hooks. Keep the checkout in place. Review and preview the appropriate script first:

```powershell
.\scripts\install_claude.ps1 -WhatIf
.\scripts\install_codex.ps1 -WhatIf
```

Remove `-WhatIf` to install the chosen agent, then restart it.

- **Claude Code:** `.\scripts\install_claude.ps1` links to `~/.claude/skills/regression-guard`; invoke `/regression-guard`. See [Claude integration](integrations/claude/README.md).
- **OpenAI Codex:** `.\scripts\install_codex.ps1` links to `~/.agents/skills/regression-guard`; invoke `$regression-guard`. See [Codex integration](integrations/codex/README.md).

Use the corresponding installer with `-Uninstall` to remove only a junction pointing to this checkout. Manual installation can copy the complete checkout into the appropriate skills directory; keep `SKILL.md`, `scripts/`, `src/`, and `references/` together.

## Optional automatic Hooks

`integrations/hooks/auto_check.py` supports Claude Code and Codex lifecycle Hooks. A `UserPromptSubmit` call with `--phase start` records a read-only Git baseline. A `Stop` call with `--phase stop` compares it and runs one TARGETED check if relevant source or test/build configuration changed. Hook setup is manual and optional. Follow your agent's current Hook configuration, pointing both events to this script with `--agent claude` or `--agent codex` and the appropriate phase. The Stop Hook needs a timeout above the test budget; allow at least 180 seconds for the default 120-second budget. Review and trust any Hook command before enabling it.

The separate Claude [PostToolUse example](integrations/claude/hooks.example.json) warns after edits to common test/build files; it does not run tests. Neither installer enables any Hook.

Set `REGRESSION_GUARD_TIMEOUT` before starting the agent to choose a 1–150 second test budget. Set `REGRESSION_GUARD_DISABLE=1`, or create an empty `%USERPROFILE%\.regression-guard.disabled` file, to disable automatic checks. Hook state lives in the system temporary directory. Results are returned to the agent for reporting, not automatic repair.

## Safety and limitations

Git inspection uses read-only commands and NUL-delimited paths. Checks disable pytest cache, bytecode writes, and third-party plugin autoload. **Test code can still write files, access credentials or services, and spawn subprocesses that outlive the timeout.** Inspect unfamiliar tests and use a disposable checkout for untrusted repositories.

Python import mapping is static and conservative. Dynamic imports, indirect dependencies, generated or unconventional tests, and JavaScript/TypeScript dependency mapping need manual review. A `package.json` test script is reported but not run automatically. Only an exact `node --test` script can run with `check --allow-node-test`. PASS means the selected files passed, not that the repository has no defects.

Automatic Hooks require a successful start baseline. They cannot attribute concurrent edits to an agent; committed changes require the baseline commit to remain available. Interpreter or Hook timeouts can prevent results from reaching the agent. Documentation-only edits and unchanged preexisting dirty files do not trigger a check.

## Instalación y uso en español

Requisitos: Windows 10/11, PowerShell, Git y Python 3.11 o superior. Para ejecutar pruebas, instala `pytest` y las dependencias de pruebas del proyecto que vas a revisar.

Clona este repositorio. Desde su raíz, previsualiza el instalador que corresponda:

```powershell
.\scripts\install_claude.ps1 -WhatIf
.\scripts\install_codex.ps1 -WhatIf
```

Quita `-WhatIf` del instalador elegido. Reinicia Claude Code o Codex e invoca `/regression-guard` o `$regression-guard`. También puedes usar el CLI sin instalar la Skill:

```powershell
python scripts/run.py analyze --repo 'C:\ruta\a\tu-proyecto'
python scripts/run.py check --repo 'C:\ruta\a\tu-proyecto' --mode targeted --timeout 120
```

FAST selecciona pruebas directas; TARGETED añade pruebas de consumidores Python detectados; FULL ejecuta todos los archivos pytest descubiertos y debe solicitarse expresamente. Los Hooks son opcionales y requieren configuración manual. Revisa las pruebas antes de ejecutarlas: pueden tener efectos secundarios.

## License

MIT. See [LICENSE](LICENSE).
