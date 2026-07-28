param()

$ErrorActionPreference = "Stop"
$WatchScript = (Resolve-Path (Join-Path $PSScriptRoot "Watch-Worker.ps1")).Path
$DashboardScript = (Resolve-Path (Join-Path $PSScriptRoot "Show-Dashboard.ps1")).Path
$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source

foreach ($Worker in @("A", "B", "C")) {
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
