param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Worker,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Codex Worker $Worker - Observer Only"
Write-Host "Observer only: closing this window does not stop the worker. Reopen this script to continue watching."
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Supervisor = Join-Path $ProjectRoot "scripts\codex_supervisor.py"
$Arguments = @($Supervisor, "watch", "--worker", $Worker, "--tail", "50")
if ($Once) {
    $Arguments += "--once"
}
. (Join-Path $PSScriptRoot "Resolve-SupervisorPython.ps1")
$Python = Resolve-SupervisorPython
& $Python @Arguments
exit $LASTEXITCODE
