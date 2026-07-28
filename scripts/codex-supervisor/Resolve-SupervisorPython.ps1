$ErrorActionPreference = "Stop"

function Resolve-SupervisorPython {
    if ($env:CODEX_SUPERVISOR_PYTHON) {
        $Override = (Resolve-Path -LiteralPath $env:CODEX_SUPERVISOR_PYTHON).Path
        return $Override
    }

    if ($env:CONDA_PREFIX -and (Split-Path -Leaf $env:CONDA_PREFIX) -eq "1999wiki") {
        $ActivePython = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path -LiteralPath $ActivePython -PathType Leaf) {
            return (Resolve-Path -LiteralPath $ActivePython).Path
        }
    }

    $Conda = Get-Command conda.exe -ErrorAction Stop
    $EnvironmentList = (& $Conda.Source env list --json | ConvertFrom-Json).envs
    $Matches = @(
        $EnvironmentList |
            Where-Object { (Split-Path -Leaf $_) -eq "1999wiki" }
    )
    if ($Matches.Count -ne 1) {
        throw "Expected exactly one Conda environment named 1999wiki."
    }
    $Python = Join-Path $Matches[0] "python.exe"
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Conda 1999wiki Python is missing: $Python"
    }
    return (Resolve-Path -LiteralPath $Python).Path
}
