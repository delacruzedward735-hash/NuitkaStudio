@echo off
cd /d "%~dp0"
echo Starting installer build. Output will also be saved to build-error.log.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { cmd /c build_professional_installer.bat 2^>^&1 | Tee-Object -FilePath build-error.log }"
pause
