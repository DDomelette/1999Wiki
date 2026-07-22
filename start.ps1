# 1999Search one-click launcher (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$PythonExe = "D:\Anaconda32024\envs\1999wiki\python.exe"
$ComposeFile = Join-Path $PSScriptRoot "infra\milvus\docker-compose.yml"
$ReactRoot = Join-Path $PSScriptRoot "frontend\react-app"
$LogRoot = Join-Path $PSScriptRoot "logs"
$StartedProcesses = @()
$ExitCode = 0

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   1999Search 一键启动 (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

function Test-PortInUse {
    param([int]$Port)
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return $null -ne ($listeners | Where-Object Port -eq $Port | Select-Object -First 1)
}

function Stop-StartedProcesses {
    param([array]$Processes)

    foreach ($process in @($Processes)) {
        if ($null -eq $process) { continue }
        try {
            $process.Refresh()
            if ($process.HasExited) { continue }
        } catch {
            # The original process object is no longer valid; never trust its PID alone.
            continue
        }
        # taskkill /T is required for npm.cmd -> node and other child process trees.
        & taskkill.exe /PID $process.Id /T /F *> $null
    }
}

function Test-NativeCancellationCode {
    param([long]$Code)
    return $Code -in @(130, -1073741510, 3221225786)
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
    $stdoutPath = Join-Path $LogRoot "$Name.stdout.log"
    $stderrPath = Join-Path $LogRoot "$Name.stderr.log"
    $process = Start-Process `
        -PassThru `
        -WindowStyle Hidden `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath
    $script:StartedProcesses += $process
    return $process
}

function Wait-AppPort {
    param(
        [string]$Name,
        [int]$Port,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 60
    )

    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        if ($Process.HasExited) {
            throw "$Name 启动进程已退出，请检查 logs\$Name.stderr.log"
        }
        if (Test-PortInUse -Port $Port) { return }
        Start-Sleep -Seconds 2
        $Process.Refresh()
    }
    throw "$Name 在 ${TimeoutSeconds}s 内未监听端口 $Port，请检查 logs\$Name.stderr.log"
}

try {
    Write-Host "[step] 使用解释器: $PythonExe" -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "找不到 1999wiki Python: $PythonExe"
    }
    & $PythonExe --version
    if (Test-NativeCancellationCode -Code $LASTEXITCODE) {
        throw [System.OperationCanceledException]::new("Python 检查已取消")
    }
    if ($LASTEXITCODE -ne 0) {
        throw "1999wiki Python 无法执行: $PythonExe"
    }

    Write-Host "[step] 检查 Python 依赖..." -ForegroundColor Yellow
    & $PythonExe scripts\check_runtime_dependencies.py
    if (Test-NativeCancellationCode -Code $LASTEXITCODE) {
        throw [System.OperationCanceledException]::new("Python 依赖检查已取消")
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python 依赖不完整。请运行: & '$PythonExe' -m pip install -r requirements.txt"
    }

    Write-Host "[step] 启动并等待 Milvus/MinIO/etcd/MySQL..." -ForegroundColor Yellow
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "找不到 Docker CLI，请先安装并启动 Docker Desktop"
    }
    & docker info --format "{{.ServerVersion}}" *> $null
    if (Test-NativeCancellationCode -Code $LASTEXITCODE) {
        throw [System.OperationCanceledException]::new("Docker 检查已取消")
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon 不可用，请先启动 Docker Desktop"
    }
    & docker compose -f $ComposeFile up -d --no-recreate --wait --wait-timeout 180
    if (Test-NativeCancellationCode -Code $LASTEXITCODE) {
        throw [System.OperationCanceledException]::new("基础设施等待已取消")
    }
    if ($LASTEXITCODE -ne 0) {
        & docker compose -f $ComposeFile ps
        throw "项目基础设施未在 180s 内全部健康。请运行 docker compose -f infra\milvus\docker-compose.yml logs"
    }
    Write-Host "[step] 基础设施就绪" -ForegroundColor Green

    foreach ($port in @(8000, 8501, 7860, 5173)) {
        if (Test-PortInUse -Port $port) {
            throw "应用端口 $port 已被占用，请先停止旧进程"
        }
    }

    Write-Host "[step] 验证 Huiji RAG provenance..." -ForegroundColor Yellow
    & $PythonExe scripts\verify_huiji_runtime.py
    if (Test-NativeCancellationCode -Code $LASTEXITCODE) {
        throw [System.OperationCanceledException]::new("Huiji RAG provenance 验证已取消")
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Huiji RAG provenance 未通过，后端和前端均未启动"
    }

    Write-Host "[step] 启动 FastAPI 后端 :8000 ..." -ForegroundColor Yellow
    $backend = Start-ManagedProcess `
        -Name "backend-8000" `
        -FilePath $PythonExe `
        -ArgumentList @("-m", "uvicorn", "backend.main:app", "--port", "8000", "--host", "127.0.0.1")

    $backendTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $backendReady = $false
    while ($backendTimer.Elapsed.TotalSeconds -lt 60) {
        $backend.Refresh()
        if ($backend.HasExited) {
            throw "FastAPI 后端进程已退出，请检查 logs\backend-8000.stderr.log"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
            if ($health.status -eq "ok" -and $health.provenance_status -eq "pass") {
                $backendReady = $true
                break
            }
        } catch [System.Management.Automation.PipelineStoppedException] {
            throw
        } catch {
            # The backend may not be accepting requests yet.
        }
        Start-Sleep -Seconds 2
    }
    if (-not $backendReady) {
        throw "FastAPI 后端在 60s 内未就绪，请检查 logs\backend-8000.stderr.log"
    }
    Write-Host "[step] 后端就绪" -ForegroundColor Green

    Write-Host "[step] 启动 Streamlit :8501 ..." -ForegroundColor Yellow
    $streamlit = Start-ManagedProcess `
        -Name "streamlit-8501" `
        -FilePath $PythonExe `
        -ArgumentList @("-m", "streamlit", "run", "frontend\streamlit_app.py", "--server.port", "8501", "--server.headless", "true")
    Wait-AppPort -Name "streamlit-8501" -Port 8501 -Process $streamlit

    Write-Host "[step] 启动 Gradio :7860 ..." -ForegroundColor Yellow
    $gradio = Start-ManagedProcess `
        -Name "gradio-7860" `
        -FilePath $PythonExe `
        -ArgumentList @("frontend\gradio_app.py")
    Wait-AppPort -Name "gradio-7860" -Port 7860 -Process $gradio

    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $npmCommand) {
        throw "找不到 npm.cmd，请先安装 Node.js"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ReactRoot "node_modules"))) {
        Write-Host "[step] 首次启动，安装 React 前端依赖..." -ForegroundColor Yellow
        & $npmCommand.Source --prefix $ReactRoot install
    } else {
        Write-Host "[step] 检查 React 前端依赖..." -ForegroundColor Yellow
        & $npmCommand.Source --prefix $ReactRoot ls --depth=0 *> $null
    }
    if (Test-NativeCancellationCode -Code $LASTEXITCODE) {
        throw [System.OperationCanceledException]::new("React 前端依赖检查已取消")
    }
    if ($LASTEXITCODE -ne 0) {
        throw "React 前端依赖检查失败，请运行 npm.cmd --prefix frontend\react-app install"
    }

    Write-Host "[step] 启动 React Vite :5173 ..." -ForegroundColor Yellow
    $vite = Start-ManagedProcess `
        -Name "vite-5173" `
        -FilePath $npmCommand.Source `
        -ArgumentList @("--prefix", $ReactRoot, "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort")
    Wait-AppPort -Name "vite-5173" -Port 5173 -Process $vite

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "   全部启动完成! 访问地址:" -ForegroundColor Green
    Write-Host "   HTML       : http://127.0.0.1:8000"
    Write-Host "   Streamlit  : http://127.0.0.1:8501"
    Write-Host "   Gradio     : http://127.0.0.1:7860"
    Write-Host "   React+Vite : http://127.0.0.1:5173"
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "   按 Ctrl+C 退出应用；数据库与 Milvus 将保持运行" -ForegroundColor Yellow

    while ($true) { Start-Sleep -Seconds 5 }
} catch [System.OperationCanceledException] {
    Write-Host "[cancel] $($_.Exception.Message)" -ForegroundColor Yellow
    $ExitCode = 130
} catch [System.Management.Automation.PipelineStoppedException] {
    [Console]::WriteLine("[cancel] 启动已取消")
    $ExitCode = 130
} catch {
    Write-Host "[错误] $($_.Exception.Message)" -ForegroundColor Red
    $ExitCode = 1
} finally {
    if ($StartedProcesses.Count -gt 0) {
        Write-Host "[stop] 正在终止本次启动的应用进程..." -ForegroundColor Yellow
        Stop-StartedProcesses -Processes $StartedProcesses
    }
    Write-Host "[stop] Milvus、MinIO、etcd 和 MySQL 保持运行" -ForegroundColor DarkGray
}

exit $ExitCode
