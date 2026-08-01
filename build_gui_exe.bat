@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run install_and_run.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
set "PYTHONUTF8=1"
python -m nuitka --mode=standalone --assume-yes-for-downloads --jobs=-2 --enable-plugin=tk-inter --include-package-data=customtkinter --include-data-dir=assets=assets --windows-console-mode=disable --windows-icon-from-ico=assets\nuitka-studio.ico --output-dir=release --output-filename=NuitkaStudio.exe --company-name="John Edward Dela Cruz" --product-name="Nuitka Studio" --file-description="Modern desktop frontend for the Nuitka Python compiler" --file-version=3.9.3.0 --product-version=3.9.3.0 run.py

if errorlevel 1 (
    echo.
    echo The build failed. Review the Nuitka error above.
    pause
    exit /b 1
)

echo.
echo Build completed in the release folder.
pause
