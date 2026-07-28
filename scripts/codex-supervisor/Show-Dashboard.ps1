param(
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Codex Supervisor Dashboard"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Supervisor = Join-Path $ProjectRoot "scripts\codex_supervisor.py"
$Arguments = @($Supervisor, "dashboard")
if (-not $Once) {
    $Arguments += "--watch"
}

if ($env:CODEX_SUPERVISOR_PYTHON) {
    & $env:CODEX_SUPERVISOR_PYTHON @Arguments
} elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3.12-64 @Arguments
} else {
    $Python = (Get-Command python.exe -ErrorAction Stop).Source
    & $Python @Arguments
}
exit $LASTEXITCODE
