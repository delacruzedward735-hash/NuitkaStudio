@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PYTHON_CMD="

py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.12"

if not defined PYTHON_CMD (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD goto :no_python

if not exist ".venv\Scripts\python.exe" (
    echo Creating the private Nuitka Studio environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" bootstrap.py
if errorlevel 1 goto :error

".venv\Scripts\python.exe" run.py
if errorlevel 1 goto :run_error
exit /b 0

:no_python
echo.
echo Python 3.10 or newer was not found.
echo Python 3.12 64-bit is recommended for Nuitka Studio.
pause
exit /b 1

:error
echo.
echo Installation failed. Review the error above, then run this file again.
pause
exit /b 1

:run_error
echo.
echo Nuitka Studio stopped with an error. Open Settings - Open diagnostics for details.
pause
exit /b 1
