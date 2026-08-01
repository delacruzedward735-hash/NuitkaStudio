# Nuitka Studio

A modern Windows and Linux desktop interface for compiling Python programs with Nuitka.

Version 2 introduces a professional sidebar layout, live environment checks,
build readiness summary, command/build-output terminal, saved presets, recent
build history, and an in-app **How to Use** guide.

Version 2.1 fixes scrollable-page navigation, makes the How to Use page display
reliably, debounces command previews, batches live compiler output, caches setup
checks, and adds fast-build controls for parallel jobs and onefile compression.

Version 2.2 hardens the application for dependable daily use: atomic settings,
corrupt-settings recovery, rotating diagnostics, full compiler-process-tree
cancellation, output-folder and disk-space preflight checks, safe advanced
arguments, exact build-history snapshots, reproducible dependency versions, and
an Open Output action after successful builds.

Version 2.3 adds phase-aware live build progress with elapsed time, reduces the
compiler-output work performed per UI cycle, disables expensive terminal text
wrapping, and integrates the official Nuitka Studio artwork into the sidebar,
window, taskbar, and compiled Windows executable.

Version 2.4 adds a dedicated application name. Nuitka Studio generates a safe
`.exe` filename from that name, reuses it for Windows product metadata, and
records both the friendly name and actual filename in build history. A custom
executable filename can still be entered when the two names should differ.

Version 2.5 finds and selects the exact executable produced by each build,
including executables nested inside Standalone `.dist` folders. When console
mode is disabled, it also reads the Windows PE header and confirms that the new
file is a GUI/no-console application. This prevents an older executable in the
top-level output folder from being tested by mistake.

Version 3.0 adds native Linux support. The interface detects its host platform:
Windows produces PE `.exe` files with Windows metadata and console controls;
Linux produces native ELF executables using GCC, Clang, or Nuitka's automatic
compiler choice. Linux builds are verified as executable ELF files and receive
an optional `.desktop` launcher with `Terminal=false`.

Version 3.1 fixes CustomTkinter's delayed Windows icon replacement, adds a
stable taskbar application identity, and replaces the sidebar's placeholder
symbols with a consistent set of native navigation icons.

Version 3.2 adds a native output-format selector. Windows builds produce `.exe`
files. Linux builds can produce either executable ELF files or installable
Debian `.deb` packages for Kali, Parrot, Debian, Ubuntu, and Mint. Debian
packages include the complete Standalone application, package metadata, desktop
launcher, optional icon, and a command under `/usr/bin`.

Version 3.2.1 improves project-environment detection. It reports whether Nuitka
is missing or installed but unable to start, shows the exact error, and can
install or repair Nuitka inside the selected `.venv` before checking again.

Version 3.2.2 fixes a false failure from the Nuitka CLI version probe by reading
the installed Nuitka version directly from the selected interpreter instead.

Version 3.2.3 automatically expands the live terminal when a build starts and
adds a control for switching between the full build output and summary.

Version 3.4 adds a dedicated **Donate** page in the sidebar with optional Ko-fi
and GCash support, a QR preview, masked public GCash details, safe copy/open
actions, and a bundled configuration file for release builds.

Version 3.5 adds a dedicated **Installer** page and a complete project-level
Windows Setup workflow. On Windows, **Windows Setup Installer (.exe)** compiles
the selected project with Nuitka, verifies the new executable, and packages it
with Inno Setup using product metadata, installation scope, shortcuts, license,
website, icon, and uninstall registration. Linux continues to provide native
ELF and Debian `.deb` output.

Version 3.6 adds **Cross Build**. It generates a GitHub Actions workflow that
builds the Windows executable on a native Windows runner and the Linux
application on a native Ubuntu runner. This provides dependable Windows-from-
Linux and Linux-from-Windows releases without pretending that Nuitka is a local
cross-compiler. The release also replaces sidebar PhotoImage objects with
CustomTkinter CTkImage objects to remove HighDPI image warnings.

Version 3.7 focuses on responsiveness and build throughput. Setup checks now use
one interpreter probe, Build no longer starts a blocking version subprocess,
verbose compiler output is batched before reaching the interface, and expensive
Cross Build previews are generated only when their page is visible. Generated
GitHub Actions workflows also use pip caching, explicit timeouts, and predictable
artifact retention.

Version 3.9.2 fixes project switching in Cross Build. Selecting a different
project root no longer keeps the previous application's entry script, icons, or
external resource paths. The Cross Build page now displays its entry script,
detects common launch files automatically, and repairs stale saved state before
workflow generation.

## Recommended setup

- Windows 10 or 11 (64-bit)
- Python 3.12 (64-bit)
- Microsoft Visual C++ Build Tools, or allow Nuitka to download MinGW64
- Inno Setup 6 when creating a Windows Setup Installer

For Linux:

- Python 3.10 or newer with Tk and venv support
- GCC/build-essential or Clang
- `patchelf` and `ccache` recommended
- `dpkg-deb` (from the `dpkg` package) for `.deb` output

Python 3.13 and newer cannot use Nuitka's `--mingw64` option. On those Python
versions, choose **Auto** or **MSVC** in the GUI.

## Quick start

1. Extract this folder.
2. On Windows, double-click `install_and_run.bat`. On Linux, run
   `chmod +x install_and_run.sh start.sh build_gui_linux.sh build_gui_deb.sh` and then
   `./install_and_run.sh`.
3. Later, use `start.bat` on Windows or `./start.sh` on Linux. The installer launcher now fingerprints `requirements.txt` and skips pip work when the private environment is already healthy.
4. Select your Python interpreter and main `.py` file.
5. Enter the **Application name** that should identify the compiled program.
6. Confirm the automatically generated executable filename.
7. Use **standalone** for the first test build.
8. When the standalone build works, switch to **onefile** for sharing.
9. On Windows, choose **Windows Setup Installer (.exe)** when you want a
   professional setup wizard. Configure publisher, website, scope, license, and
   shortcuts under **Installer**. Inno Setup 6 is required.
10. On Linux, choose **Debian package (.deb)** when you want an installer for a
    Debian-based system. Set its Package ID and Maintainer under **App Identity**.
11. To build for the other operating system, open **Cross Build**, select the
    project root and targets, generate the workflow, commit it with the project,
    then run **Nuitka Studio Cross Build** from the GitHub Actions tab.

You can open **How to Use** from the sidebar or the `?` button at any time. It
contains the complete workflow, compiler guidance, and solutions for common
missing-module, missing-resource, console, and output-size problems.

If `py -3.12` is unavailable, install Python 3.12 from python.org and enable
"Add Python to PATH" during installation.

## Important usage notes

- Select the interpreter from the project you are compiling. Choose
  `.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on Linux.
- When an entry script is selected, Nuitka Studio searches nearby `.venv`,
  `venv`, and `env` folders and offers to use the detected project interpreter.
  It warns before using Nuitka Studio's private environment for an unrelated
  project because that environment may not contain the project's dependencies.
- Windows icons must be real `.ico` files. Linux launchers accept PNG, SVG, or XPM.
- Add data folders such as `assets`, templates, or static files in the
  **Packages & Data** tab.
- Only force packages when Nuitka does not detect them automatically.
- The build starts in the same directory as the selected entry script, which
  preserves most relative-path project layouts.
- The command preview can be copied for use in PowerShell or Command Prompt.
- Cancel stops Nuitka and the SCons/compiler child processes started for that
  build; it does not affect unrelated Python or compiler processes.
- Advanced arguments cannot duplicate options already controlled by the GUI.
- Builds are blocked when the output location is not writable. A warning is
  shown when less than approximately 1 GB is available.

## Settings and diagnostics

Nuitka Studio stores its personal settings and rotating error log under:

```text
%APPDATA%\NuitkaStudio
```

Use **Settings → Open diagnostics** to open that folder. Settings are written
atomically. If a settings file becomes invalid, it is preserved with a
`settings.corrupt-<date>.json` filename and safe defaults are loaded.

## Live progress

Nuitka does not expose a reliable overall percentage for every compiler and
plugin combination. Nuitka Studio therefore detects major phases—Python
analysis, C generation, native compilation, linking, and onefile packaging—and
shows a smoothly advancing phase-based bar plus real elapsed time. The final
success or failure still comes from Nuitka's process exit code.

## CustomTkinter example

Enable:

- **Tkinter plugin**
- **Include CustomTkinter data**

If your program uses Pillow, tkinterdnd2, fitz, or pdf2docx and Nuitka reports a
missing dynamic import, add the specific package under **Include package**.

## Running from a terminal

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

## Compile the GUI itself

After installation, double-click `build_gui_exe.bat` on Windows, run
`./build_gui_linux.sh` for a Linux ELF build, or run `./build_gui_deb.sh` for an
installable Linux package. The Standalone build is placed in `release`.
Standalone mode is intentional because it starts faster and is easier to
troubleshoot than a Onefile wrapper.

Install a generated Debian package from its output folder with:

```bash
sudo apt install ./package-name_version_arch.deb
```

## Windows project setup installers

When running on Windows, select **Windows Setup Installer (.exe)** under
**Build → Output format**. Nuitka Studio first creates and verifies the selected
Standalone or Onefile application, then invokes Inno Setup to create a setup
wizard with Add/Remove Programs registration and an uninstaller.

Installer settings are available under the dedicated **Installer** page. See
`docs/guides/INSTALLER_SETUP_GUIDE.md` for the complete workflow and application-specific
limitations.

## Native target rule

Nuitka Studio builds for the operating system where it is running. Run Studio
on Windows to create Windows executables and on Linux to create Linux ELF or
Debian package output. It does not rename, emulate, or cross-compile one
platform's binary as another.

## Tests

```powershell
python -m unittest discover -s tests -v
```
