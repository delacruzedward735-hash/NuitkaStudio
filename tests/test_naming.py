# SPDX-License-Identifier: MIT
import unittest
from pathlib import Path

from nuitka_gui.naming import debian_package_id, executable_name, infer_application_name


class NamingTests(unittest.TestCase):
    def test_generic_entry_uses_project_folder(self):
        self.assertEqual(infer_application_name(Path(r"C:\Projects\NexaConvert\main.py")), "NexaConvert")

    def test_specific_entry_uses_script_name(self):
        self.assertEqual(infer_application_name(Path(r"C:\Projects\Tools\image_converter.py")), "image converter")

    def test_executable_name_removes_invalid_windows_characters(self):
        self.assertEqual(executable_name('Nexa: Convert / Pro'), "Nexa- Convert - Pro.exe")

    def test_reserved_windows_name_is_made_safe(self):
        self.assertEqual(executable_name("CON"), "CON App.exe")

    def test_linux_executable_has_no_exe_extension(self):
        self.assertEqual(executable_name("NexaConvert", "linux"), "NexaConvert")
        self.assertEqual(executable_name("NexaConvert.exe", "linux"), "NexaConvert")

    def test_debian_package_id_is_lowercase_and_safe(self):
        self.assertEqual(debian_package_id("Nexa Convert Pro!"), "nexa-convert-pro")
        self.assertEqual(debian_package_id("  "), "application")


if __name__ == "__main__":
    unittest.main()
