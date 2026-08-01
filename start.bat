@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
if not exist ".venv\Scripts\python.exe" (
    echo The environment is not installed yet.
    echo Run install_and_run.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 (
    echo.
    echo Nuitka Studio stopped with an error. Open Settings - Open diagnostics.
    pause
    exit /b 1
)
