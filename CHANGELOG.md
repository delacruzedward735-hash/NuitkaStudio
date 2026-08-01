# Changelog

## 3.9.3 - Open-source readiness

- Replaced the previous restrictive custom license with the OSI-approved MIT License.
- Added public repository documentation for contributing, conduct, security, support, releases, branding, authorship, architecture, and development.
- Added GitHub issue forms, pull-request guidance, CODEOWNERS, cross-platform CI, and Dependabot updates.
- Added third-party dependency notices and a prominent independent-project disclaimer.
- Added a repository audit script for version consistency, secrets, personal paths, Python compilation, and automated tests.
- Preserved the detailed historical README under `docs/RELEASE_HISTORY.md` and replaced the root README with a public project overview.
- Updated Windows, Linux, Debian, citation, and installer metadata to version 3.9.3.

## 3.9.2 - Cross-project switching fix

- Fixed Cross Build reusing the previous application's entry script after a different project root was selected.
- Added a visible Entry script selector directly to the Cross Build page.
- Automatically detects conventional project entry files such as `main.py`, `app.py`, `run.py`, and `src/main.py`.
- Clears stale icons, installer-license paths, and resource mappings that belong to the previously selected project.
- Updates the active output folder and application name when switching to another project.
- Repairs mismatched saved Cross Build state when the page is opened or a workflow is generated.
- Added regression coverage for the NexaConvert-to-SwiftShare project-switching bug.
- Expanded the automated test suite from 82 to 86 tests.

## 3.9.1 - Windows uninstall reliability

- Added a stable Windows application mutex so Setup and Uninstall can detect a running Nuitka Studio process.
- Enabled Restart Manager support and uninstall logging in Windows installer scripts.
- Preserved the existing AppId and append-mode uninstall log for safe upgrades.
- Fixed the Start Menu shortcut file/folder name conflict.
- Removed the obsolete Quick Launch shortcut.
- Strengthened generated project installer defaults for upgrades and uninstall diagnostics.

## 3.9.0

- Audited startup, navigation, persistence, and shutdown behavior.
- Loads the saved appearance mode before widget construction, eliminating the full-window theme redraw seen during startup.
- Keeps the root window hidden until the first page is fully laid out, preventing intermediate layouts from flashing on screen.
- Builds only the Build page at launch; Cross Build, Packages, Resources, App Identity, Installer, History, Settings, How to Use, and Donate are created once on first use.
- Navigation now hides only the previous page instead of reconfiguring every page, reducing redraw work.
- Preserves package, package-data, advanced-argument, resource, and history settings with lazy page creation.
- Skips unchanged settings writes, avoiding unnecessary JSON serialization, filesystem flushes, and `fsync` calls on exit.
- Hides the application immediately on exit and terminates an active compiler process in a bounded background cleanup step.
- The install-and-run bootstrap now checks package availability without importing heavy GUI and compiler modules on every launch.
- Updated Windows, Linux, Debian, and self-installer version metadata to 3.9.0.

## 3.8.0

- Fixed mouse-wheel and touchpad scrolling across all pages containing `CTkScrollableFrame`.
- Added one centralized scroll-event router so multiple scrollable pages no longer overwrite each other's global bindings.
- Added Linux Button-4/Button-5, Wayland/Windows MouseWheel, and macOS wheel normalization.
- Scroll events now target the area under the pointer and bubble to an outer frame when an inner frame is already at its boundary.
- Preserved independent scrolling inside terminal and workflow-preview text boxes.
- Added regression tests for cross-platform wheel normalization.
- Updated Windows, Linux, Debian, and self-installer version metadata to 3.8.0.

## 3.7.0

- Added a requirements fingerprint bootstrap so repeated `install_and_run` launches skip unnecessary pip upgrades and reinstalls.
- Reduced startup environment checks from three Python subprocesses to one JSON probe.
- Removed the synchronous Python-version subprocess from the Build button path, preventing interface freezes before compilation.
- Deferred Cross Build workflow generation until its page is visible and its configuration has changed.
- Cached command-preview, workflow-preview, and Inno Setup discovery results to reduce repeated widget and filesystem work while typing.
- Batched verbose compiler output before sending it to Tk, keeping the interface responsive during noisy Nuitka and Inno Setup runs.
- Added unbuffered UTF-8 subprocess environments for faster, cleaner live build logs.
- Added pip caching, job timeouts, and artifact-retention settings to generated GitHub Actions workflows.
- Accepts GitHub repository URLs ending in `.git` when opening the Actions page.
- Closes image files immediately after loading them to avoid retaining file handles.
- Expanded the automated regression suite from 62 to 69 tests.
- Updated Windows, Linux, Debian, and self-installer version metadata to 3.7.0.

## 3.6.0

- Added a dedicated Cross Build item to the left navigation.
- Added GitHub Actions workflow generation for native Windows and Linux builds from either host operating system.
- Added Windows-only, Linux-only, and combined build targets with selectable Python version and optional requirements file.
- Reuses Nuitka Studio package, resource, application identity, mode, jobs, and advanced build settings in the generated workflow.
- Validates that the entry script, resources, and platform icons are inside the project repository before workflow creation.
- Packages Linux outputs as a tar.gz artifact so executable permissions survive download.
- Added manual workflow dispatch and optional automatic builds on pushes to main or master.
- Replaced Tkinter PhotoImage sidebar usage with CTkImage to remove CustomTkinter HighDPI image warnings.
- Added cross-build workflow regression tests and expanded the suite from 57 to 62 tests.
- Updated Windows, Linux, Debian, and self-installer version metadata to 3.6.0.

## 3.5.0

- Added a dedicated Installer item to the left navigation.
- Added `Windows Setup Installer (.exe)` as a Windows output format.
- Added automatic Inno Setup 6 detection plus optional manual `ISCC.exe` selection.
- Added project-level installer settings for publisher, website, license, install scope, Start Menu shortcut, desktop shortcut, and launch-after-install.
- Added professional Inno Setup script generation for both Nuitka Standalone and Onefile builds.
- Verifies the newly compiled Windows executable before packaging and verifies that the expected setup file was created.
- Integrated setup packaging into live logs, cancellation, progress, build history, completion dialogs, and Show built output.
- Added `docs/guides/INSTALLER_SETUP_GUIDE.md` and automated Windows installer-script regression tests.
- Expanded the test suite from 51 to 57 tests.
- Updated Windows, Linux, and self-installer version metadata to 3.5.0.

## 3.4.0

- Added a dedicated Donate item to the left navigation.
- Added a polished support page with Ko-fi and GCash provider cards.
- Added optional bundled Ko-fi URL, GCash recipient details, and GCash QR preview configuration.
- Masks the public GCash number while retaining a one-click copy action.
- Added donation safety reminders and graceful unconfigured states.
- Added `docs/guides/DONATION_SETUP.md` and `assets/donation_config.json` for release configuration.
- Updated Windows, Linux, and installer version metadata to 3.4.0.

## 3.2.3

- Fixed the live build textbox collapsing to zero height beneath the Build Summary card.
- Live build output now expands automatically when compilation starts.
- Added an Expand/Show summary control for switching between the full terminal and build summary.
- The expanded terminal remains visible after completion so errors can be reviewed immediately.

## 3.2.2

- Fixed a false “Nuitka installed but cannot start” result for usable project environments.
- Replaced the slow Nuitka CLI version subprocess with a fast version lookup inside the selected interpreter.
- Kept missing-package and damaged-installation reporting without blocking a valid Nuitka installation.

## 3.2.1

- Fixed project virtual environments remaining on “Nuitka not checked” after Nuitka was installed.
- Setup checks now distinguish missing Nuitka from an installed copy that cannot start.
- Added the exact interpreter path and underlying Nuitka error to the setup dialog.
- Added an optional Install/Repair action that installs Nuitka into the selected project environment, then verifies it again.
- Successful setup checks are cached for only five minutes; failed checks are always re-run.

## 3.2.0

- Added a host-aware output-format selector: Windows EXE, Linux ELF, or Linux Debian package.
- Added rootless `.deb` creation through `dpkg-deb` for Kali, Parrot, Debian, Ubuntu, and Mint.
- Packages include the exact verified Nuitka build, a desktop entry, optional icon, and `/usr/bin` launcher.
- Added Debian package ID, maintainer, section, description, version, architecture, and installed-size metadata.
- Integrated Debian packaging into the live build log, phase progress bar, completion dialog, build history, and Show built output action.
- Added `build_gui_deb.sh` so Nuitka Studio can compile and package itself on Linux.
- Added validation that prevents misleading Windows/Linux cross-target selections.
- Added real `dpkg-deb` regression coverage and expanded the test suite to 47 tests.

## 3.1.0

- Fixed CustomTkinter overwriting the Nuitka Studio window and taskbar icon after startup.
- Added a stable Windows AppUserModelID for correct taskbar icon grouping.
- Reapplies the branded multi-resolution ICO after CustomTkinter's delayed default-icon callback.
- Replaced placeholder sidebar symbols with seven consistent line-icon assets.
- Preserved the hexagonal Nuitka Studio brand artwork in the window, taskbar, sidebar, and compiled executable.

## 3.0.0

- Added native Linux support while preserving the complete Windows build workflow.
- Added automatic host detection: Windows produces PE `.exe` files and Linux produces native ELF executables.
- Added Linux Auto, GCC, and Clang compiler choices.
- Removed Windows-only console, icon, and version-resource arguments from Linux commands.
- Added Linux `.venv/bin/python` project-environment detection.
- Added Linux ELF and executable-permission verification after successful builds.
- Added generated `.desktop` launchers with `Terminal=false` and optional copied PNG/SVG/XPM icons.
- Added Linux install, start, and self-build shell scripts.
- Added platform-safe output naming, command previews, preset migration, history, and diagnostics paths.

## 2.5.0

- Fixed output navigation so Studio finds and selects the exact EXE created by the current build.
- Prevented stale executables in the top-level output folder from being mistaken for a fresh Standalone build.
- Added Windows PE subsystem verification for builds using Disable console mode.
- Added a clear verified GUI/no-console completion state.
- Added guidance when an external converter process, rather than the compiled GUI itself, opens a terminal.

## 2.4.0

- Added a dedicated Application name field to Project setup.
- Automatically generates a safe `.exe` filename from the application name.
- Uses the application name as Windows Product name metadata when no override is supplied.
- Infers a useful name from the project folder when the entry script is `main.py`, `app.py`, or `run.py`.
- Shows both the friendly application name and executable filename in build history.
- Preserves custom executable filenames and migrates existing saved presets.

## 2.3.0

- Added a phase-aware live build progress bar and elapsed-time display.
- Added progress states for preparing, analysis, C generation, compilation, linking, packaging, success, cancellation, and failure.
- Reduced queue work per Tk event-loop cycle for smoother interaction during noisy builds.
- Disabled terminal word wrapping to reduce redraw overhead.
- Added the custom Nuitka Studio icon to the window, sidebar, taskbar, and compiled EXE.
- Added multi-resolution ICO and optimized PNG assets.
- Added progress-detection and asset regression tests.
- Added automatic project virtual-environment detection and wrong-environment warnings.

## 2.2.0

- Added atomic settings writes and corrupt-settings backup recovery.
- Added rotating local diagnostic logs and unexpected-UI-error handling.
- Added full build process-tree cancellation on Windows and Unix-like systems.
- Added output write-access and low-disk-space preflight checks.
- Added exact active-build snapshots for reliable history records.
- Added Open Output and Open Diagnostics actions.
- Added package, metadata, filename, resource destination, and advanced-option validation.
- Added duplicate resource protection and a proper empty-resource state.
- Pinned compatible production dependency versions.
- Expanded automated tests.

## 2.1.0

- Fixed How to Use and other scrollable-page navigation.
- Batched live output and debounced command preview refreshes.
- Added setup-check caching, fast jobs, and onefile no-compression options.

## 2.0.0

- Introduced the modern Nuitka Studio interface and in-app guide.
