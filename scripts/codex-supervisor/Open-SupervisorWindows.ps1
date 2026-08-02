param()

$ErrorActionPreference = "Stop"
$WatchScript = (Resolve-Path (Join-Path $PSScriptRoot "Watch-Worker.ps1")).Path
$DashboardScript = (Resolve-Path (Join-Path $PSScriptRoot "Show-Dashboard.ps1")).Path
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Supervisor = Join-Path $ProjectRoot "scripts\codex_supervisor.py"
$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
. (Join-Path $PSScriptRoot "Resolve-SupervisorPython.ps1")
$Python = Resolve-SupervisorPython
$WorkerListJson = & $Python $Supervisor worker-list --json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$WorkerList = $WorkerListJson | ConvertFrom-Json

foreach ($Worker in $WorkerList.workers) {
    $Arguments = @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ('"{0}"' -f $WatchScript),
        "-Worker",
        $Worker
    )
    Start-Process -FilePath $PowerShell -ArgumentList $Arguments -WindowStyle Normal
}

$DashboardArguments = @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    ('"{0}"' -f $DashboardScript)
)
Start-Process -FilePath $PowerShell -ArgumentList $DashboardArguments -WindowStyle Normal
