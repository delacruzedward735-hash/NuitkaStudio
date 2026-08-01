# Contributing to Nuitka Studio

Thank you for helping improve Nuitka Studio. Contributions are welcome from beginners, testers, technical writers, designers, and experienced Python developers.

## Before starting

- Search existing issues before opening a duplicate.
- Keep one issue or pull request focused on one problem.
- For a significant UI redesign, architecture change, or new packaging backend, open a proposal issue first.
- Never include secrets, private certificates, personal payment credentials, or unredacted private logs.

## Development environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate       # Windows
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run.py
```

Linux contributors may need:

```bash
sudo apt install python3-tk python3-venv build-essential xvfb
```

## Testing

Run all repository checks before opening a pull request:

```bash
python scripts/open_source_check.py
```

Or run the main test suite directly:

```bash
python -m unittest discover -s tests -v
```

Changes to Windows installer generation should include tests in `tests/test_windows_installer.py`. Changes to Cross Build should include tests in `tests/test_cross_build.py`. Platform-specific behavior should be tested on the real target operating system whenever possible.

## Code guidelines

- Support Python 3.10 or newer unless a change is discussed first.
- Prefer standard-library solutions when they are clear and reliable.
- Keep long-running work away from the Tk main thread.
- Avoid global mouse-wheel bindings that break nested or inactive pages.
- Use `pathlib.Path` for filesystem operations.
- Validate user-controlled paths and command arguments before starting a process.
- Never use `shell=True` for project-controlled command arguments.
- Preserve current settings migrations and cross-project state isolation.
- Add or update docstrings for non-obvious behavior.

## Commit and pull-request guidance

Use a clear commit summary, for example:

```text
Fix stale resources after switching projects
Add Fedora packaging documentation
Improve cancellation on Windows
```

A pull request should include:

- The problem being solved
- The implementation approach
- Tests performed
- Screenshots for visible UI changes
- Known limitations or platform gaps

## Licensing contributions

By submitting a contribution, you confirm that you have the right to provide it and agree that it will be distributed under this repository's MIT License. Preserve required notices for third-party material and describe the source in the pull request.

## Conduct

All contributors must follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
