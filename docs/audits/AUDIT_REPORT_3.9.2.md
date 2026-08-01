# Nuitka Studio 3.9.2 — Cross Build State Audit

## Reported issue

Selecting SwiftShare as the Cross Build project root still used NexaConvert's
saved entry script. The workflow validator then rejected the script because it
was outside the selected repository.

## Root cause

The Cross Build project root and the Build page entry script were independent
saved fields. The Cross Build page did not display or update the entry script
when another project root was selected.

## Fixes

- Added the active Entry script field to Cross Build.
- Added automatic discovery for common Python launch files.
- Synchronizes the active Build configuration when another project is selected.
- Resets the output filename, product name, Debian package ID, and output folder
  to the newly selected project.
- Clears icons, installer licenses, and resource mappings outside the new root.
- Rechecks the project state before writing a workflow, including pasted paths.

## Validation

- 86 automated unit and regression tests pass.
- Python source compilation succeeds.
- Linux shell launch/build scripts pass `bash -n` syntax checks.
- ZIP integrity and executable permissions are verified before release.

A full Windows GUI and Inno Setup cycle still requires testing on Windows.
