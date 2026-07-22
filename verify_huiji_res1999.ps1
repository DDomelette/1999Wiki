# 1999Search HuijiWiki local integrity verifier launcher
param(
    [string]$Out = "data\huiji\res1999",
    [string]$Db = "",
    [switch]$SkipResourceFiles,
    [switch]$SkipResourceHash,
    [int]$IssueLimit = 200,
    [switch]$Json
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
    "scripts\verify_huiji_res1999.py",
    "--out", $Out,
    "--issue-limit", "$IssueLimit"
)

if ($Db) {
    $argsList += @("--db", $Db)
}
if ($SkipResourceFiles) {
    $argsList += "--skip-resource-files"
}
if ($SkipResourceHash) {
    $argsList += "--skip-resource-hash"
}
if ($Json) {
    $argsList += "--json"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   HuijiWiki res1999 integrity verifier" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "[step] Python: $py" -ForegroundColor Yellow
Write-Host "[step] Output: $Out" -ForegroundColor Yellow
Write-Host "[step] Verify resource files: $(-not $SkipResourceFiles)" -ForegroundColor Yellow
Write-Host "[step] Verify resource hash: $(-not $SkipResourceHash)" -ForegroundColor Yellow
Write-Host "[step] Running verifier..." -ForegroundColor Yellow

& $py @argsList
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host "[ok] Integrity verification passed." -ForegroundColor Green
} else {
    Write-Host "[error] Integrity verification failed. Review the issue list above." -ForegroundColor Red
}
exit $code
