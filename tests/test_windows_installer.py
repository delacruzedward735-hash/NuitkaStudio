# SPDX-License-Identifier: MIT
from pathlib import Path
import tempfile
import unittest

from nuitka_gui.windows_installer import (
    WindowsInstallerConfig,
    find_inno_setup_compiler,
    generate_inno_script,
    installer_output_filename,
    prepare_windows_installer,
)


class WindowsInstallerTests(unittest.TestCase):
    def test_output_filename_is_safe(self):
        self.assertEqual(
            installer_output_filename("Nexa Convert: Pro", "1.2.3.4"),
            "Nexa-Convert-Pro-Setup-1.2.3.4.exe",
        )

    def test_generates_standalone_installer_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dist = root / "NexaConvert.dist"
            dist.mkdir()
            executable = dist / "NexaConvert.exe"
            executable.write_bytes(b"MZdemo")
            icon = root / "icon.ico"
            icon.write_bytes(b"ico")
            license_file = root / "LICENSE.txt"
            license_file.write_text("License", encoding="utf-8")

            script, output = generate_inno_script(
                WindowsInstallerConfig(
                    executable=executable,
                    output_directory=root / "output",
                    application_name="NexaConvert",
                    version="1.2.3.4",
                    publisher="John Edward Dela Cruz",
                    website="https://myportfoliohub.online",
                    icon_path=icon,
                    license_path=license_file,
                    mode="standalone",
                )
            )

            self.assertIn("WizardStyle=modern", script)
            self.assertIn('Source: "', script)
            self.assertIn("NexaConvert.dist\\*", script)
            self.assertIn('DestDir: "{app}"', script)
            self.assertIn("PrivilegesRequired=admin", script)
            self.assertIn("CloseApplications=yes", script)
            self.assertIn("RestartManagerSupport=yes", script)
            self.assertIn("UsePreviousAppDir=yes", script)
            self.assertIn("UninstallLogging=yes", script)
            self.assertIn("UninstallLogMode=append", script)
            self.assertIn("SetupIconFile=", script)
            self.assertIn("LicenseFile=", script)
            self.assertIn("AppPublisherURL=https://myportfoliohub.online", script)
            self.assertEqual(output.name, "NexaConvert-Setup-1.2.3.4.exe")

    def test_generates_current_user_onefile_script_without_optional_shortcuts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "Demo.exe"
            executable.write_bytes(b"MZdemo")
            script, _output = generate_inno_script(
                WindowsInstallerConfig(
                    executable=executable,
                    output_directory=root / "output",
                    application_name="Demo",
                    version="1.0.0.0",
                    publisher="Publisher",
                    mode="onefile",
                    install_scope="current_user",
                    desktop_shortcut=False,
                    start_menu_shortcut=False,
                    launch_after_install=False,
                )
            )
            self.assertIn(r"DefaultDirName={localappdata}\Programs\Demo", script)
            self.assertIn("PrivilegesRequired=lowest", script)
            self.assertNotIn("[Tasks]", script)
            self.assertNotIn("[Icons]", script)
            self.assertNotIn("[Run]", script)

    def test_prepares_script_with_custom_compiler(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "Demo.exe"
            executable.write_bytes(b"MZdemo")
            compiler = root / "ISCC.exe"
            compiler.write_bytes(b"fake")
            self.assertEqual(find_inno_setup_compiler(compiler), compiler)

            prepared = prepare_windows_installer(
                WindowsInstallerConfig(
                    executable=executable,
                    output_directory=root / "output",
                    application_name="Demo",
                    version="1.0.0.0",
                    publisher="Publisher",
                    mode="onefile",
                    compiler_path=compiler,
                )
            )
            try:
                self.assertTrue(prepared.script_path.is_file())
                self.assertEqual(prepared.command[0], str(compiler.resolve()))
                self.assertEqual(prepared.output_path.name, "Demo-Setup-1.0.0.0.exe")
            finally:
                prepared.cleanup()


if __name__ == "__main__":
    unittest.main()
