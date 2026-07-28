param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Worker
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Supervisor = Join-Path $ProjectRoot "scripts\codex_supervisor.py"
$TaskFile = Join-Path $ProjectRoot ".codex-supervisor\workers\$Worker\approved-task.md"

if ($env:CODEX_SUPERVISOR_PYTHON) {
    & $env:CODEX_SUPERVISOR_PYTHON $Supervisor start --worker $Worker --task-file $TaskFile
} elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3.12-64 $Supervisor start --worker $Worker --task-file $TaskFile
} else {
    $Python = (Get-Command python.exe -ErrorAction Stop).Source
    & $Python $Supervisor start --worker $Worker --task-file $TaskFile
}
exit $LASTEXITCODE
