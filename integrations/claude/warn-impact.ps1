$ErrorActionPreference = 'SilentlyContinue'
$null = [Console]::In.ReadToEnd()
$paths = @(git diff --name-only --; git diff --cached --name-only --)
$critical = @($paths | Where-Object { $_ -match '(^|/)(pyproject\.toml|pytest\.ini|conftest\.py|package\.json|setup\.cfg|tox\.ini)$' })
if ($critical.Count -gt 0) {
    @{ hookSpecificOutput = @{ hookEventName = 'PostToolUse'; additionalContext = "Regression Guard: critical configuration changed ($($critical -join ', ')). Review targeted coverage before finishing." } } | ConvertTo-Json -Compress -Depth 4
}
exit 0
