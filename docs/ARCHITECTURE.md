# Architecture

## Main layers

- `nuitka_gui/app.py` — CustomTkinter application, navigation, settings, lifecycle, build orchestration, and UI state
- `nuitka_gui/command_builder.py` — validated Nuitka command construction
- `nuitka_gui/environment_check.py` — Python and Nuitka environment inspection
- `nuitka_gui/runtime.py` — process, output, path, executable, and platform utilities
- `nuitka_gui/progress.py` — phase detection for live build progress
- `nuitka_gui/windows_installer.py` — generated Inno Setup project installers
- `nuitka_gui/deb_package.py` — Debian package staging and creation
- `nuitka_gui/cross_build.py` — GitHub Actions workflow generation and repository-path validation

## Runtime model

Tk owns the main UI thread. Compiler and packaging operations run in child processes and background threads. Output is batched before being placed on the UI queue to reduce redraw pressure. Cancellation terminates the build process tree rather than unrelated Python or compiler processes.

## State model

Settings are stored atomically in the user's application-data directory. Pages are created lazily and cached after first use. Cross-project switching validates that entry scripts, icons, licenses, and resources belong to the active project root before workflow generation.

## Packaging model

Compilation and installer packaging are separate stages. A generated installer is created only after the newly produced executable has been located and verified. Cross-platform output uses native CI runners instead of unsupported local binary conversion.
