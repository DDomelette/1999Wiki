param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Worker,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Codex Worker $Worker - Observer Only"
Write-Host "只读观察窗口：关闭本窗口不会停止 worker；重新运行本脚本可接续查看。"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Supervisor = Join-Path $ProjectRoot "scripts\codex_supervisor.py"
$Arguments = @($Supervisor, "watch", "--worker", $Worker, "--tail", "50")
if ($Once) {
    $Arguments += "--once"
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
