# Development Guide

## Entry points

- `python run.py` starts the application.
- `python bootstrap.py` checks or prepares the private environment used by launch scripts.

## Adding a setting

1. Add a Tk variable and default.
2. Load it with backward-compatible handling.
3. Include it in the serialized settings snapshot.
4. Add validation before it affects a command or filesystem operation.
5. Add a migration or safe fallback when old settings may contain another type.
6. Add tests for loading, saving, and malformed input.

## Adding a Nuitka option

Keep command generation in `nuitka_gui/command_builder.py`. Prevent advanced arguments from duplicating options already controlled by the GUI. Use a list of arguments and `subprocess` without `shell=True`.

## Adding a packaging backend

A backend should:

- Validate all required tools and paths
- Stage output in a temporary or controlled build directory
- Avoid writing into the user's source tree unexpectedly
- Verify the final artifact
- Surface useful logs and errors
- Support cancellation where practical
- Include target-native automated and manual tests

## UI performance

Do not perform interpreter checks, compiler discovery, directory scans, or process waits directly on the Tk event loop. Debounce expensive previews and update large logs in batches.

## Manual testing matrix

At minimum, test normal startup, first navigation to each lazy page, project switching, settings persistence, standalone compilation, one-file compilation, cancellation, build failure, successful output reveal, closing while idle, and closing during a build.
