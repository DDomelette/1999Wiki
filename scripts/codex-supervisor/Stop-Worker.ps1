param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Worker
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Supervisor = Join-Path $ProjectRoot "scripts\codex_supervisor.py"

if ($env:CODEX_SUPERVISOR_PYTHON) {
    & $env:CODEX_SUPERVISOR_PYTHON $Supervisor stop --worker $Worker
} elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3.12-64 $Supervisor stop --worker $Worker
} else {
    $Python = (Get-Command python.exe -ErrorAction Stop).Source
    & $Python $Supervisor stop --worker $Worker
}
exit $LASTEXITCODE
