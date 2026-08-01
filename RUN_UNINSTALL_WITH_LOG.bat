@echo off
setlocal EnableExtensions
set "LOG_FILE=%USERPROFILE%\Desktop\NuitkaStudio-uninstall.log"
set "UNINSTALLER="

for %%U in (
  "%ProgramFiles%\Nuitka Studio\unins*.exe"
  "%ProgramFiles(x86)%\Nuitka Studio\unins*.exe"
  "%LocalAppData%\Programs\Nuitka Studio\unins*.exe"
) do (
  if not defined UNINSTALLER if exist "%%~fU" set "UNINSTALLER=%%~fU"
)

if not defined UNINSTALLER (
  echo Nuitka Studio's Inno Setup uninstaller was not found.
  echo Install version 3.9.3 over the existing installation, then try again.
  pause
  exit /b 1
)

echo Closing Nuitka Studio before uninstalling is required.
echo Uninstaller: %UNINSTALLER%
echo Log: %LOG_FILE%
echo.
start /wait "" "%UNINSTALLER%" /LOG="%LOG_FILE%"
set "RESULT=%ERRORLEVEL%"

echo.
if "%RESULT%"=="0" (
  echo Uninstall completed successfully.
) else (
  echo Uninstall returned error code %RESULT%.
  echo Open this log and send the last error lines for diagnosis:
  echo %LOG_FILE%
)
pause
exit /b %RESULT%
