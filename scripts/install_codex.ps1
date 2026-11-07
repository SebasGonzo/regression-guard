param([switch]$Uninstall, [switch]$WhatIf)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$parent = Join-Path $env:USERPROFILE '.agents\skills'
$dest = Join-Path $parent 'regression-guard'
if ($Uninstall) {
    if (-not (Test-Path -LiteralPath $dest)) { Write-Host 'Not installed.'; exit 0 }
    $item = Get-Item -LiteralPath $dest -Force
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Target -ne $source) { throw "Refusing to remove a non-owned installation: $dest" }
    if ($WhatIf) { Write-Host "Would remove junction $dest"; exit 0 }
    Remove-Item -LiteralPath $dest -Force
    Write-Host "Removed $dest"
    exit 0
}
if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md'))) { throw 'SKILL.md missing.' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3.11+ missing.' }
$version = & python -c 'import sys; print(sys.version_info >= (3,11))'
if ($version -ne 'True') { throw 'Python 3.11+ required.' }
if (Test-Path -LiteralPath $dest) { throw "Destination exists; preserved without changes: $dest" }
if ($WhatIf) { Write-Host "Would create junction $dest -> $source"; exit 0 }
New-Item -ItemType Directory -Path $parent -Force | Out-Null
New-Item -ItemType Junction -Path $dest -Target $source | Out-Null
Write-Host "Installed $dest -> $source. Restart Codex and invoke regression-guard explicitly."
