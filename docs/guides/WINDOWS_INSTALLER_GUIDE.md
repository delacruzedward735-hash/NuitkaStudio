# Build the Professional Windows Installer

## Result

The release process creates:

- `release\run.dist\NuitkaStudio.exe` — compiled desktop application
- `installer-output\NuitkaStudio-Setup-3.9.3.exe` — professional Windows installer

The installer uses administrator permission and installs the application in:

`C:\Program Files\Nuitka Studio`

It also creates a Start Menu entry, optional desktop shortcut, uninstall entry, creator attribution, and a portfolio shortcut to `https://myportfoliohub.online`.

## Requirements

1. Windows 10 or Windows 11, 64-bit
2. Python 3.12 recommended
3. Internet connection during the first build
4. Inno Setup 6

## One-command build

Double-click:

`build_professional_installer.bat`

The script creates a virtual environment, installs dependencies, compiles the application with Nuitka, and builds the setup EXE with Inno Setup.

## Creator information

- Creator: John Edward Dela Cruz
- Portfolio: https://myportfoliohub.online
- Product: Nuitka Studio 3.9.3
