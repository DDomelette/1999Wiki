param(
    [Parameter(Mandatory = $true)]
    [string]$Worker
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Supervisor = Join-Path $ProjectRoot "scripts\codex_supervisor.py"
. (Join-Path $PSScriptRoot "Resolve-SupervisorPython.ps1")
$Python = Resolve-SupervisorPython
& $Python $Supervisor worker-validate --worker $Worker --json | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python $Supervisor stop --worker $Worker
exit $LASTEXITCODE
