@echo off
set "HUIJI_SELECTED_PYTHON="

if defined HUIJI_CRAWLER_PYTHON (
    if exist "%HUIJI_CRAWLER_PYTHON%" set "HUIJI_SELECTED_PYTHON=%HUIJI_CRAWLER_PYTHON%"
    if defined HUIJI_SELECTED_PYTHON exit /b 0
)

for /f "usebackq delims=" %%P in (`py -3.12-64 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined HUIJI_SELECTED_PYTHON set "HUIJI_SELECTED_PYTHON=%%P"
if defined HUIJI_SELECTED_PYTHON exit /b 0

for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined HUIJI_SELECTED_PYTHON set "HUIJI_SELECTED_PYTHON=%%P"
if defined HUIJI_SELECTED_PYTHON exit /b 0

echo [error] Windows CPython 3.12 x64 was not found. 1>&2
exit /b 8
