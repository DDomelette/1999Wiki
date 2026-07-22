@echo off
chcp 65001 >nul
setlocal

set PROJ_ROOT=%~dp0
cd /d "%PROJ_ROOT%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJ_ROOT%crawl_huiji_res1999.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [错误] HuijiWiki crawler launcher exited with code %EXIT_CODE%
    pause
)
exit /b %EXIT_CODE%
