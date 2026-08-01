# Project Installer Setup

Nuitka Studio 3.9.3 can compile a Python application and then package the new
Windows build as a professional **Setup `.exe`**.

## Where the option appears

On Windows, open **Build** and choose:

```text
Output format → Windows Setup Installer (.exe)
```

The left navigation also includes **Installer**, where you can configure:

- Publisher and website
- Inno Setup compiler (`ISCC.exe`), when automatic detection is unavailable
- Optional license document
- All-users installation under Program Files or current-user installation
- Start Menu shortcut
- Optional desktop shortcut
- Optional launch-after-install action

## Required software

Windows Setup output requires **Inno Setup 6**. Nuitka Studio searches:

- A manually selected `ISCC.exe`
- The system `PATH`
- Standard Inno Setup installation folders

A normal Windows EXE can still be compiled without Inno Setup.

## Build workflow

1. Configure and test the project in **Standalone** mode.
2. Set the product metadata under **App Identity**.
3. Configure the setup under **Installer**.
4. Select **Windows Setup Installer (.exe)** under Build.
5. Click **Build setup**.
6. Nuitka compiles the application.
7. Inno Setup packages the newly verified executable and its `.dist` files.
8. Test the setup on a separate Windows computer before publishing it.

The generated file uses this naming pattern:

```text
ApplicationName-Setup-1.0.0.0.exe
```

## Platform rule

Windows Setup `.exe` output must be built on Windows. On Linux, use the native
**Debian package (`.deb`)** output for Debian, Ubuntu, Mint, Kali, and Parrot.
Nuitka Studio does not rename or cross-compile a Linux executable into a Windows
installer.

## Application-specific setup work

The automatic setup is suitable for ordinary desktop applications. A project
may still require custom post-install behavior for services, drivers, firewall
rules, file associations, external runtimes, or database initialization.
Application-generated data should normally be stored in the user's AppData
folder, not inside Program Files.
