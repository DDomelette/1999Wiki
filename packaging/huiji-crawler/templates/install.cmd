@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
set "ROOT=%~dp0"
for %%I in ("%ROOT%.") do set "ROOT=%%~fI"
pushd "%ROOT%" || exit /b 8

call "%ROOT%\bootstrap\select-python.cmd"
if errorlevel 1 (
    popd
    exit /b 8
)

"%HUIJI_SELECTED_PYTHON%" "%ROOT%\bootstrap\install.py" --root "%ROOT%"
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
