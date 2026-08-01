# SPDX-License-Identifier: MIT
import json
import subprocess
import unittest
from unittest.mock import patch

from nuitka_gui.environment_check import (
    check_python_environment,
    nuitka_install_command,
    parse_python_version,
)


class EnvironmentCheckTests(unittest.TestCase):
    @patch("nuitka_gui.environment_check.subprocess.run")
    def test_reports_nuitka_missing_from_selected_environment(self, run):
        payload = {
            "version": "Python 3.14.6",
            "version_info": [3, 14, 6],
            "nuitka_installed": False,
            "nuitka_version": "",
            "nuitka_issue": "",
        }
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(payload) + "\n", "")
        result = check_python_environment(r"C:\Project\.venv\Scripts\python.exe")
        self.assertTrue(result["python"])
        self.assertFalse(result["nuitka"])
        self.assertFalse(result["nuitka_installed"])
        self.assertIn("not installed", str(result["nuitka_issue"]))
        run.assert_called_once()

    @patch("nuitka_gui.environment_check.subprocess.run")
    def test_distinguishes_installed_but_broken_nuitka(self, run):
        payload = {
            "version": "Python 3.14.6",
            "version_info": [3, 14, 6],
            "nuitka_installed": True,
            "nuitka_version": "",
            "nuitka_issue": "Package metadata is damaged",
        }
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(payload) + "\n", "")
        result = check_python_environment("python")
        self.assertTrue(result["nuitka_installed"])
        self.assertFalse(result["nuitka"])
        self.assertEqual(result["nuitka_issue"], "Package metadata is damaged")

    @patch("nuitka_gui.environment_check.subprocess.run")
    def test_reports_working_nuitka_version(self, run):
        payload = {
            "version": "Python 3.12.9",
            "version_info": [3, 12, 9],
            "nuitka_installed": True,
            "nuitka_version": "4.1.3",
            "nuitka_issue": "",
        }
        run.return_value = subprocess.CompletedProcess([], 0, "harmless warning\n" + json.dumps(payload) + "\n", "")
        result = check_python_environment("python")
        self.assertTrue(result["nuitka"])
        self.assertEqual(result["nuitka_version"], "4.1.3")
        self.assertEqual(result["version_info"], [3, 12, 9])

    @patch("nuitka_gui.environment_check.subprocess.run")
    def test_handles_invalid_probe_output(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "not json\n", "")
        result = check_python_environment("python")
        self.assertFalse(result["python"])
        self.assertIn("valid setup information", str(result["nuitka_issue"]))

    def test_parse_python_version(self):
        self.assertEqual(parse_python_version([3, 12, 9]), (3, 12, 9))
        self.assertEqual(parse_python_version("Python 3.13.4"), (3, 13, 4))
        self.assertEqual(parse_python_version("Unknown"), (0, 0, 0))

    def test_install_command_uses_exact_interpreter(self):
        python = r"C:\Project\.venv\Scripts\python.exe"
        command = nuitka_install_command(python)
        self.assertEqual(command[:4], [python, "-m", "pip", "install"])


if __name__ == "__main__":
    unittest.main()
