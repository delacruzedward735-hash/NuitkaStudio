# Nuitka Studio 3.9.2 — Cross Project Switching Fix

## Fixed bug

Cross Build previously stored the project root separately from the Build page's
entry script. Selecting a new project root could therefore leave an older
application's `main.py` active. The workflow validator correctly rejected the
mismatch, but the interface did not switch the active project automatically.

## New behavior

- The Cross Build page now shows the active Entry script.
- Selecting another project root searches for `main.py`, `app.py`, `run.py`,
  `main_onefile.py`, `__main__.py`, `src/main.py`, or `src/app.py`.
- The detected script becomes the active Build and Cross Build entry script.
- The output folder and generated application name are moved to the new project.
- Icons, resource mappings, and installer-license paths outside the new project
  are cleared so they cannot leak from a previous application.
- Pasted project roots are repaired again before workflow generation.

## Example

Changing the project root from NexaConvert to SwiftShare now changes:

```text
NexaConvert/main.py
```

to the detected file inside:

```text
SwiftShare/main.py
```

without requiring the user to return to the Build page first.
