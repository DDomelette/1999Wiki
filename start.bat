@echo off
chcp 65001 >nul
setlocal

set PROJ_ROOT=%~dp0
cd /d "%PROJ_ROOT%"

echo ========================================
echo   1999Search 一键启动
echo ========================================

REM 解析 langchain env 的 python.exe (不依赖 conda activate)
for /f "delims=" %%i in ('conda run -n langchain python -c "import sys; print(sys.executable)" 2^>nul') do set PY=%%i
if not defined PY (
    echo [错误] 无法定位 conda 环境 langchain 的 python, 请确认 conda 在 PATH 且环境存在
    pause
    exit /b 1
)
echo [step] 使用解释器: %PY%

REM 1. Huiji provenance gate
echo [step] 验证 Huiji RAG provenance...
"%PY%" scripts\verify_huiji_runtime.py
if errorlevel 1 (
    echo [错误] Huiji RAG provenance 未通过，后端和前端均未启动
    pause
    exit /b 1
)

REM 固定关键端口,避免 Vite 自动漂移到 5174 或连到旧后端
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
    echo [错误] 端口 8000 已被占用, 请先停止旧后端进程
    pause
    exit /b 1
)
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
    echo [错误] 端口 5173 已被占用, 请先停止旧 Vite 进程
    pause
    exit /b 1
)

REM 2. 后端
echo [step] 启动 FastAPI 后端 :8000 ...
start "1999Search-Backend" /min cmd /c ""%PY%" -m uvicorn backend.main:app --port 8000 --host 127.0.0.1"

REM 3. 健康检查 (60s)
set /a tries=0
:wait_health
set /a tries+=1
if %tries% gtr 30 (
    echo [错误] 后端 60s 内未就绪, 请检查 Milvus、embedding key 与日志
    taskkill /fi "WINDOWTITLE eq 1999Search-Backend*" /t /f >nul 2>nul
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
"%PY%" -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)); raise SystemExit(0 if d.get('status')=='ok' and d.get('provenance_status')=='pass' else 1)" >nul 2>nul
if errorlevel 1 goto wait_health
echo [step] 后端就绪

REM 4. 延迟启动前端
set /a delay=3
echo [step] %delay%s 后启动 Streamlit :8501 ...
timeout /t %delay% /nobreak >nul
start "1999Search-Streamlit" /min cmd /c ""%PY%" -m streamlit run frontend\streamlit_app.py --server.port 8501 --server.headless true"

echo [step] %delay%s 后启动 Gradio :7860 ...
timeout /t %delay% /nobreak >nul
start "1999Search-Gradio" /min cmd /c ""%PY%" frontend\gradio_app.py"

echo [step] 启动 React Vite :5173 ...
if not exist "frontend\react-app\node_modules" (
    echo [step] 首次启动, 安装 React 前端依赖...
    pushd frontend\react-app
    call npm.cmd install
    popd
)
timeout /t 3 /nobreak >nul
start "React Vite" /min cmd /c "cd frontend\react-app && npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort"

echo ========================================
echo   全部启动完成! 访问地址:
echo   HTML       : http://localhost:8000
echo   Streamlit  : http://localhost:8501
echo   Gradio     : http://localhost:7860
echo    React+Vite : http://localhost:5173
echo ========================================
echo   关闭本窗口不会停止服务。停止请关闭弹出的最小化窗口。
pause
endlocal
