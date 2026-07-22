# 1999Search 一键启动 (PowerShell, 退出时清理子进程)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   1999Search 一键启动 (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

function Test-PortInUse([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Stop-StartedJobs {
    param([array]$Jobs)
    $Jobs | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
}

# 解析 langchain env python.exe (不依赖 conda activate)
$py = (conda run -n langchain python -c "import sys; print(sys.executable)" 2>$null | Out-String).Trim()
if (-not $py -or -not (Test-Path $py)) {
    Write-Host "[错误] 无法定位 conda 环境 langchain 的 python" -ForegroundColor Red
    Read-Host; exit 1
}
Write-Host "[step] 使用解释器: $py" -ForegroundColor Yellow

Write-Host "[step] 验证 Huiji RAG provenance..." -ForegroundColor Yellow
& $py scripts\verify_huiji_runtime.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] Huiji RAG provenance 未通过，后端和前端均未启动" -ForegroundColor Red
    Read-Host
    exit 1
}

$jobs = @()
if (Test-PortInUse 8000) {
    Write-Host "[错误] 端口 8000 已被占用, 请先停止旧后端进程" -ForegroundColor Red
    Read-Host; exit 1
}
Write-Host "[step] 启动 FastAPI 后端 :8000 ..." -ForegroundColor Yellow
$jobs += Start-Process -PassThru -WindowStyle Minimized -FilePath $py -ArgumentList "-m","uvicorn","backend.main:app","--port","8000","--host","127.0.0.1"

$tries = 0
while ($tries -lt 30) {
    $tries++
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
        if ($h.status -eq "ok" -and $h.provenance_status -eq "pass") { break }
    } catch { Start-Sleep -Seconds 2 }
}
if ($tries -ge 30) {
    Write-Host "[错误] 后端 60s 未就绪" -ForegroundColor Red
    Stop-StartedJobs $jobs
    Read-Host; exit 1
}
Write-Host "[step] 后端就绪" -ForegroundColor Green

$delay = 3
Write-Host "[step] ${delay}s 后启动 Streamlit :8501 ..." -ForegroundColor Yellow
Start-Sleep -Seconds $delay
$jobs += Start-Process -PassThru -WindowStyle Minimized -FilePath $py -ArgumentList "-m","streamlit","run","frontend\streamlit_app.py","--server.port","8501","--server.headless","true"

Write-Host "[step] ${delay}s 后启动 Gradio :7860 ..." -ForegroundColor Yellow
Start-Sleep -Seconds $delay
$jobs += Start-Process -PassThru -WindowStyle Minimized -FilePath $py -ArgumentList "frontend\gradio_app.py"

# 检测并启动 React Vite
if (-not (Test-Path "frontend\react-app\node_modules")) {
    Write-Host "[step] 首次启动, 安装 React 前端依赖..." -ForegroundColor Yellow
    Push-Location frontend\react-app
    & npm install
    Pop-Location
}
if (Test-PortInUse 5173) {
    Write-Host "[错误] 端口 5173 已被占用, 请先停止旧 Vite 进程" -ForegroundColor Red
    Stop-StartedJobs $jobs
    Read-Host; exit 1
}
Write-Host "[step] ${delay}s 后启动 React Vite :5173 ..." -ForegroundColor Yellow
Start-Sleep -Seconds $delay
$jobs += Start-Process -PassThru -WindowStyle Minimized -FilePath "npm.cmd" -ArgumentList "--prefix","frontend\react-app","run","dev","--","--host","127.0.0.1","--port","5173","--strictPort"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   全部启动完成! 访问地址:" -ForegroundColor Green
Write-Host "   HTML       : http://localhost:8000"
Write-Host "   Streamlit  : http://localhost:8501"
Write-Host "   Gradio     : http://localhost:7860"
Write-Host "   React+Vite : http://localhost:5173"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   按 Ctrl+C 退出将终止所有子进程" -ForegroundColor Yellow

try {
    while ($true) { Start-Sleep -Seconds 5 }
} finally {
    Write-Host "[stop] 正在终止子进程..." -ForegroundColor Yellow
    Stop-StartedJobs $jobs
}
