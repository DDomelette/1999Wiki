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
. (Join-Path $PSScriptRoot "Resolve-SupervisorPython.ps1")
$Python = Resolve-SupervisorPython
& $Python $Supervisor worker-list --json | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python @Arguments
exit $LASTEXITCODE
