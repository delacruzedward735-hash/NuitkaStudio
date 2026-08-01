@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Nuitka Studio - Build Real Windows Installer

set "APP_VERSION=3.9.3"
set "DIST_DIR=release\run.dist"
set "INSTALLER_FILE=installer-output\NuitkaStudio-Setup-%APP_VERSION%.exe"

echo ============================================================
echo  NUITKA STUDIO - REAL WINDOWS INSTALLER BUILDER
echo  Creator: John Edward Dela Cruz
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python Launcher was not found.
    echo Install Python 3.12 or 3.13 from python.org and enable "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Creating a Python virtual environment...
    py -3.12 -m venv .venv 2>nul
    if errorlevel 1 py -3.13 -m venv .venv 2>nul
    if errorlevel 1 py -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo [1/5] Existing virtual environment found.
)

call ".venv\Scripts\activate.bat"
set "PYTHONUTF8=1"

echo [2/5] Installing compiler requirements...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [3/5] Compiling Nuitka Studio...
if exist "release" rmdir /s /q "release"
python -m nuitka ^
  --mode=standalone ^
  --assume-yes-for-downloads ^
  --remove-output ^
  --jobs=-2 ^
  --enable-plugin=tk-inter ^
  --include-package-data=customtkinter ^
  --include-data-dir=assets=assets ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\nuitka-studio.ico ^
  --output-dir=release ^
  --output-filename=NuitkaStudio.exe ^
  --company-name="John Edward Dela Cruz" ^
  --product-name="Nuitka Studio" ^
  --file-description="Professional desktop frontend for building Python applications with Nuitka" ^
  --copyright="Copyright (c) 2026 John Edward Dela Cruz" ^
  --trademarks="Created by John Edward Dela Cruz - myportfoliohub.online" ^
  --file-version=3.9.3.0 ^
  --product-version=3.9.3.0 ^
  run.py
if errorlevel 1 goto :fail

if not exist "%DIST_DIR%\NuitkaStudio.exe" (
    for /d %%D in ("release\*.dist") do (
        if exist "%%~fD\NuitkaStudio.exe" set "DIST_DIR=%%~fD"
    )
)
if not exist "%DIST_DIR%\NuitkaStudio.exe" (
    echo [ERROR] The compiled application folder could not be found.
    goto :fail
)

echo [4/5] Checking Inno Setup...
call :find_iscc
if not defined ISCC (
    where winget >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Inno Setup 6 is not installed and winget is unavailable.
        echo Install Inno Setup 6, then run this file again:
        echo https://jrsoftware.org/isdl.php
        start "" "https://jrsoftware.org/isdl.php"
        pause
        exit /b 2
    )

    echo Inno Setup is missing. Installing it automatically...
    winget install --id JRSoftware.InnoSetup --exact --accept-package-agreements --accept-source-agreements --silent
    if errorlevel 1 (
        echo [ERROR] Automatic Inno Setup installation failed.
        echo Install it manually, then run this file again.
        start "" "https://jrsoftware.org/isdl.php"
        pause
        exit /b 2
    )
    call :find_iscc
)

if not defined ISCC (
    echo [ERROR] Inno Setup was installed but ISCC.exe was not found.
    pause
    exit /b 2
)

echo [5/5] Creating the real Setup installer...
if exist "installer-output" rmdir /s /q "installer-output"
"%ISCC%" /DSourceDist="%DIST_DIR%" installer.iss
if errorlevel 1 goto :fail

if not exist "%INSTALLER_FILE%" (
    echo [ERROR] Inno Setup completed but the installer file was not found.
    goto :fail
)

echo.
echo ============================================================
echo  SUCCESS - REAL INSTALLER CREATED
echo.
echo  %CD%\%INSTALLER_FILE%
echo.
echo  Upload this Setup EXE to your website.
echo  It installs into C:\Program Files\Nuitka Studio
echo ============================================================
start "" explorer.exe /select,"%CD%\%INSTALLER_FILE%"
pause
exit /b 0

:find_iscc
set "ISCC="
for %%P in (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
) do if exist "%%~P" set "ISCC=%%~P"
exit /b 0

:fail
echo.
echo ============================================================
echo  BUILD FAILED

echo  Read the error shown above. A file named build-error.log can

echo  be created by running BUILD_INSTALLER_WITH_LOG.bat.
echo ============================================================
pause
exit /b 1
