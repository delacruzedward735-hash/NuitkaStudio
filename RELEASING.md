# Release Process

1. Update `APP_VERSION` in `nuitka_gui/app.py` and `__version__` in `nuitka_gui/__init__.py`.
2. Update Windows, Debian, and installer version fields in the build scripts.
3. Add a release entry to `CHANGELOG.md`.
4. Run:

   ```bash
   python scripts/open_source_check.py
   ```

5. Test source startup on Linux and Windows.
6. Build and test a native standalone application on each target platform.
7. Build, install, upgrade, and uninstall the Windows Setup package on Windows.
8. Build, install, upgrade, and remove the Debian package on a clean Debian-based system.
9. Generate a Cross Build workflow and verify downloaded Windows and Linux artifacts.
10. Create a source archive without `.venv`, build output, private settings, secrets, or real payment credentials unless intentionally public.
11. Tag the release using `v<version>` and publish checksums with the release assets.

Do not call a release stable until the target-native installer cycles have been completed successfully.
