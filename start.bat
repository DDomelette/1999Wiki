@echo off
chcp 65001 >nul
setlocal

REM Delegate to the PowerShell launcher so both entry points share one implementation.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
set "START_EXIT=%ERRORLEVEL%"

endlocal & exit /b %START_EXIT%
