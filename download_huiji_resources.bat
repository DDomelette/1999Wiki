@echo off
chcp 65001 >nul
setlocal

set PROJ_ROOT=%~dp0
cd /d "%PROJ_ROOT%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJ_ROOT%download_huiji_resources.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [error] HuijiWiki resource downloader exited with code %EXIT_CODE%
    pause
)
exit /b %EXIT_CODE%
