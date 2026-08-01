# Nuitka Studio 3.9.1 — Windows Uninstall Fix

This maintenance release fixes the Windows Setup/uninstall path.

## Fixed

- Nuitka Studio now creates a stable Windows application mutex.
- Setup and Uninstall detect when Nuitka Studio is still running and ask the user to close it before continuing.
- Installer upgrades use the existing install directory and uninstall log.
- Installer and uninstaller logging are enabled.
- The Start Menu shortcut layout no longer creates a file/folder name conflict.
- The obsolete Quick Launch shortcut was removed.
- Generated project installers now enable stronger Restart Manager and uninstall-log settings.

## Test an uninstall with logging

Close Nuitka Studio, then run its uninstaller with:

```bat
"C:\Program Files\Nuitka Studio\unins000.exe" /LOG="%USERPROFILE%\Desktop\NuitkaStudio-uninstall.log"
```

The uninstaller filename can be `unins001.exe` or another number when several Inno Setup applications share a directory. Use the uninstall shortcut in the Start Menu if unsure.

## Upgrade note

Install version 3.9.1 over version 3.9.0. The fixed installer keeps the same AppId, so it updates the existing installation instead of creating a second product entry.
