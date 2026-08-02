param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryRoot,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$BaseCommit,
    [Parameter(Mandatory = $true)]
    [string[]]$AllowedFile,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $PSScriptRoot "Resolve-SupervisorPython.ps1")
$Python = Resolve-SupervisorPython
$Arguments = @(
    "-m",
    "src.codex_supervisor.task_receipts",
    "identity",
    "--repository-root",
    ([IO.Path]::GetFullPath($RepositoryRoot)),
    "--base-commit",
    $BaseCommit,
    "--output",
    ([IO.Path]::GetFullPath($OutputPath))
)
foreach ($Path in $AllowedFile) {
    $Arguments += @("--allowed-file", $Path)
}
Push-Location $ProjectRoot
try {
    & $Python @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
