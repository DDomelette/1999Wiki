@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
set "ROOT=%~dp0"
for %%I in ("%ROOT%.") do set "ROOT=%%~fI"
set "VENV_PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "INSTALL_MARKER=%ROOT%\.venv\.huiji-crawler-install.v1.json"
pushd "%ROOT%" || exit /b 8

if not exist "%VENV_PYTHON%" (
    echo [error] Crawler environment is missing. Run install.cmd. 1>&2
    popd
    exit /b 8
)
if not exist "%INSTALL_MARKER%" (
    echo [error] Crawler install marker is missing. Run install.cmd. 1>&2
    popd
    exit /b 8
)

"%VENV_PYTHON%" "%ROOT%\bootstrap\install.py" --root "%ROOT%" --check-marker
if errorlevel 1 (
    popd
    exit /b 8
)

"%VENV_PYTHON%" "%ROOT%\bootstrap\package_verify.py" --root "%ROOT%" --critical-only
if errorlevel 1 (
    popd
    exit /b 4
)

"%VENV_PYTHON%" -m src.huiji_crawler_tool %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
