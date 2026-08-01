# SPDX-License-Identifier: MIT
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bootstrap


class BootstrapTests(unittest.TestCase):
    def test_fingerprint_changes_with_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            requirements = Path(directory) / "requirements.txt"
            requirements.write_text("nuitka==1\n", encoding="utf-8")
            with patch.object(bootstrap, "REQUIREMENTS", requirements):
                first = bootstrap.dependency_fingerprint()
                requirements.write_text("nuitka==2\n", encoding="utf-8")
                second = bootstrap.dependency_fingerprint()
            self.assertNotEqual(first, second)

    def test_dependencies_ready_requires_matching_marker_and_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "marker"
            marker.write_text("expected\n", encoding="utf-8")
            with (
                patch.object(bootstrap, "MARKER", marker),
                patch.object(bootstrap, "REQUIRED_IMPORTS", ("json", "pathlib")),
            ):
                self.assertTrue(bootstrap.dependencies_ready("expected"))
                self.assertFalse(bootstrap.dependencies_ready("different"))

    def test_dependencies_ready_rejects_missing_package_without_importing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "marker"
            marker.write_text("expected\n", encoding="utf-8")
            with (
                patch.object(bootstrap, "MARKER", marker),
                patch.object(bootstrap, "REQUIRED_IMPORTS", ("missing_package",)),
                patch.object(bootstrap.importlib.util, "find_spec", return_value=None) as find_spec,
            ):
                self.assertFalse(bootstrap.dependencies_ready("expected"))
                find_spec.assert_called_once_with("missing_package")


if __name__ == "__main__":
    unittest.main()
