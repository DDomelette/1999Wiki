# 1999Search HuijiWiki crawler development launcher
param(
    [ValidateSet("DryRun", "Small", "Full")]
    [string]$Mode = "DryRun",
    [ValidateSet("", "Requests", "Browser", "Edge")]
    [string]$Transport = "",
    [int]$Limit = 20,
    [string]$Config = "",
    [string]$Out = "",
    [string]$Namespaces = "",
    [string]$ExpectedUser = "",
    [string]$BrowserProfile = "",
    [string]$EdgeProfile = "",
    [int]$EdgePort = 0,
    [string]$EdgeExecutable = "",
    [int]$LogEvery = 0,
    [double]$Sleep = -1,
    [switch]$BrowserHeadless,
    [switch]$NoBrowserVerify,
    [switch]$Force,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Resolve-CrawlerPython {
    if ($env:HUIJI_CRAWLER_PYTHON) {
        $explicit = $env:HUIJI_CRAWLER_PYTHON
        if (-not (Test-Path -LiteralPath $explicit -PathType Leaf)) {
            throw "HUIJI_CRAWLER_PYTHON does not name an existing file"
        }
        return (Resolve-Path -LiteralPath $explicit).Path
    }

    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $candidate = (& $launcher.Source -3.12-64 -c "import sys; print(sys.executable)" 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $pathPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pathPython -and (Test-Path -LiteralPath $pathPython.Source -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $pathPython.Source).Path
    }

    throw "No Python candidate found. Set HUIJI_CRAWLER_PYTHON or install CPython 3.12 x64."
}

function Build-CrawlerArgs {
    $arguments = @("-m", "src.huiji_crawler_tool", "crawl", "--resume")
    if ($Config) { $arguments += @("--config", $Config) }
    if ($Out) { $arguments += @("--out", $Out) }
    if ($Namespaces) { $arguments += @("--namespaces", $Namespaces) }
    if ($ExpectedUser) { $arguments += @("--expected-user", $ExpectedUser) }
    if ($Transport) { $arguments += @("--transport", $Transport.ToLowerInvariant()) }
    if ($LogEvery -gt 0) { $arguments += @("--log-every", "$LogEvery") }
    if ($Sleep -ge 0) { $arguments += @("--sleep", "$Sleep") }

    if ($Mode -eq "DryRun") {
        $arguments += "--dry-run"
    } elseif ($Mode -eq "Small") {
        $arguments += @("--include-file-manifest", "--limit", "$Limit")
    } elseif ($Mode -eq "Full") {
        $arguments += "--include-file-manifest"
    }

    if ($Force) { $arguments += "--force" }
    if ($Quiet) { $arguments += "--quiet" }
    if ($BrowserProfile) { $arguments += @("--browser-profile", $BrowserProfile) }
    if ($EdgeProfile) { $arguments += @("--edge-profile", $EdgeProfile) }
    if ($EdgePort -gt 0) { $arguments += @("--edge-port", "$EdgePort") }
    if ($EdgeExecutable) { $arguments += @("--edge-executable", $EdgeExecutable) }
    if ($BrowserHeadless) { $arguments += "--browser-headless" }
    if ($NoBrowserVerify) { $arguments += "--no-browser-verify" }
    return $arguments
}

try {
    $python = Resolve-CrawlerPython
    $crawlerArgs = Build-CrawlerArgs
    & $python @crawlerArgs
    exit $LASTEXITCODE
} catch {
    Write-Error $_.Exception.Message
    exit 8
}
