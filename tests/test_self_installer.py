# SPDX-License-Identifier: MIT
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SelfInstallerTests(unittest.TestCase):
    def test_self_installer_has_running_app_detection_and_logging(self):
        script = (ROOT / "installer.iss").read_text(encoding="utf-8")
        self.assertIn("AppMutex=PypyProject.NuitkaStudio.App,Global\\PypyProject.NuitkaStudio.App", script)
        self.assertIn("CloseApplications=yes", script)
        self.assertIn("RestartManagerSupport=yes", script)
        self.assertIn("UninstallLogging=yes", script)
        self.assertIn("UninstallLogMode=append", script)

    def test_start_menu_entries_share_the_group_folder(self):
        script = (ROOT / "installer.iss").read_text(encoding="utf-8")
        self.assertIn('Name: "{group}\\{#MyAppName}"', script)
        self.assertIn('Name: "{group}\\Creator Portfolio"', script)
        self.assertIn('Name: "{group}\\Uninstall {#MyAppName}"', script)
        self.assertNotIn("quicklaunchicon", script)
        self.assertNotIn('Name: "{autoprograms}\\{#MyAppName}"', script)

    def test_application_uses_matching_mutex_name(self):
        source = (ROOT / "nuitka_gui" / "app.py").read_text(encoding="utf-8")
        self.assertIn('WINDOWS_APP_MUTEX = "PypyProject.NuitkaStudio.App"', source)
        self.assertIn("create_windows_app_mutexes()", source)


if __name__ == "__main__":
    unittest.main()
