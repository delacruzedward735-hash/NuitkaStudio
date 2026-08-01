# Nuitka Studio 3.9.1 — Windows Installer and Uninstaller Audit

## Reported problem

The Windows Setup package could install, but uninstall could fail or leave an inconsistent Start Menu layout.

## Findings

1. The application did not expose a Windows mutex, so Inno Setup Uninstall had no reliable built-in way to detect that Nuitka Studio was still running.
2. The self-installer created a shortcut named `Nuitka Studio` directly in the Start Menu and also tried to create a folder with the same name for other shortcuts. That file/folder collision was invalid.
3. The obsolete Quick Launch task added another unnecessary uninstall target.
4. Installer logging and append-mode uninstall-log settings were not explicit.

## Corrections

- Added matching local and Global Windows mutexes to the application and `AppMutex` to `installer.iss`.
- Moved all Start Menu entries into the configured `{group}` folder.
- Removed Quick Launch integration.
- Enabled Restart Manager support and uninstall logging.
- Kept the existing fixed AppId so version 3.9.1 repairs/upgrades version 3.9.0 instead of creating a second installed product.
- Strengthened generated project installer upgrade/logging defaults.

## Validation performed in this environment

- Python bytecode compilation: passed.
- 82 automated unit tests: passed.
- Linux shell syntax checks: passed.
- ZIP integrity and executable permission checks: passed.

## Native Windows validation still required

The final Setup EXE and uninstaller must be built and tested on Windows because Inno Setup and Windows file-lock behavior cannot be executed in this Linux environment.
