# Nuitka Studio 3.9.0 — Performance and Lifecycle Audit

## Scope

The audit reviewed application startup, page construction, navigation, settings persistence, background setup checks, compiler-process handling, and application shutdown.

## Findings and fixes

### 1. Full interface redraw during startup — fixed

The application always created its widgets in light mode, then loaded the saved appearance mode afterward. A saved dark theme therefore forced CustomTkinter to redraw the complete interface and made startup look like several windows were reloading.

The saved theme is now read before the root window and widgets are created.

### 2. Every page was constructed before first display — fixed

All ten pages, including the large Donate, Help, Settings, Cross Build, and Installer pages, were created synchronously during startup. The application now constructs only the Build page initially. Every other page is created once when first opened and remains available for instant later navigation.

### 3. Intermediate layouts were visible while starting — fixed

The root window is now hidden during initial construction and shown only after the first page has completed layout.

### 4. Navigation reconfigured all pages — fixed

Every navigation click previously removed every page from the grid before restoring the selected page. Navigation now hides only the previous page and shows the requested page.

### 5. Windows installer discovery ran too early — fixed

Inno Setup discovery can scan Windows installation directories. It is now deferred until the Installer page is opened, a Setup build is selected, or a custom compiler path is supplied.

### 6. Settings were rewritten even when unchanged — fixed

Settings writes use a stable signature. Closing the application without configuration changes now skips the JSON rewrite, flush, and filesystem synchronization.

### 7. Exit could remain visible while compiler cleanup completed — fixed

The window now disappears immediately after exit is confirmed. If a build is active, process-tree termination continues in a bounded non-UI cleanup thread instead of holding the visible window open for up to four seconds.

### 8. Lazy pages needed persistent text state — fixed

Package inclusions, package-data inclusions, advanced arguments, resources, and history remain available before and after their pages are first opened. Existing 3.8.0 settings remain compatible.

### 9. Repeated refresh work — reduced

The command preview now reuses one collected configuration per refresh. Startup no longer performs an unnecessary data-list refresh, and normal EXE editing avoids installer scans.

### 10. Install-and-run dependency checks imported heavy modules — fixed

The bootstrap previously imported CustomTkinter, Pillow, and Nuitka on every install-and-run launch even when the environment marker was current. It now checks package availability with import specifications and avoids executing those modules until the application actually starts.

## Validation

- 79 automated tests passed, including lifecycle, lazy-page, unchanged-settings, and fast-bootstrap regression tests.
- Python source compilation passed.
- Linux shell-script syntax checks passed.
- Git diff whitespace validation passed.
- Release metadata was updated consistently to 3.9.0.

A final visual launch and installer build should still be tested on the target Linux Mint and Windows machines because this audit environment did not contain the full graphical dependency environment or Inno Setup.
