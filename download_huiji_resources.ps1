# 1999Search HuijiWiki resource downloader launcher
param(
    [int]$Workers = 2,
    [int]$Limit = 0,
    [string]$Out = "data\huiji\res1999",
    [int]$LogEvery = 100,
    [double]$Sleep = 0.2,
    [int]$Retries = 2,
    [double]$Timeout = 30.0,
    [string[]]$MimePrefix = @(),
    [switch]$IncludeFailed
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Resolve-CondaPython {
    $py = (conda run -n 1999wiki python -c "import sys; print(sys.executable)" 2>$null | Out-String).Trim()
    if (-not $py -or -not (Test-Path $py)) {
        Write-Host "[error] Cannot locate python.exe in conda environment 1999wiki" -ForegroundColor Red
        exit 1
    }
    return $py
}

$py = Resolve-CondaPython
$argsList = @(
    "scripts\download_huiji_resources.py",
    "--out", $Out,
    "--workers", "$Workers",
    "--log-every", "$LogEvery",
    "--sleep", "$Sleep",
    "--retries", "$Retries",
    "--timeout", "$Timeout"
)

if ($Limit -gt 0) {
    $argsList += @("--limit", "$Limit")
}
if ($IncludeFailed) {
    $argsList += "--include-failed"
}
foreach ($prefix in $MimePrefix) {
    if ($prefix) {
        $argsList += @("--mime-prefix", $prefix)
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   HuijiWiki res1999 resource downloader" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "[step] Python: $py" -ForegroundColor Yellow
Write-Host "[step] Output: $Out" -ForegroundColor Yellow
Write-Host "[step] Workers: $Workers" -ForegroundColor Yellow
Write-Host "[step] Running downloader..." -ForegroundColor Yellow

& $py @argsList
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host "[ok] Resource downloader finished." -ForegroundColor Green
} else {
    Write-Host "[warn] Resource downloader exited with code $code. Re-run with -IncludeFailed to retry failed resources." -ForegroundColor Yellow
}
exit $code
