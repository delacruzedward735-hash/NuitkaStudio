# SPDX-License-Identifier: MIT
import tempfile
import unittest
from pathlib import Path

from nuitka_gui.command_builder import BuildConfig, DataMapping
from nuitka_gui.cross_build import (
    CrossBuildError,
    detect_project_entry_script,
    generate_cross_build_workflow,
    path_is_inside_project,
    write_cross_build_workflow,
)


class CrossBuildTests(unittest.TestCase):
    def make_project(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
        (root / "requirements.txt").write_text("pillow\n", encoding="utf-8")
        (root / "assets").mkdir()
        (root / "assets" / "icon.ico").write_bytes(b"ico")
        (root / "assets" / "icon.png").write_bytes(b"png")
        return temporary, root

    def config(self, root: Path, **changes):
        values = dict(
            python_executable="python",
            entry_script=str(root / "main.py"),
            output_directory=str(root / "dist"),
            output_filename="Demo.exe",
            application_name="Demo",
            mode="onefile",
            jobs="-2",
            onefile_no_compression=True,
            company_name="Code Dev",
            product_name="Demo",
            file_version="1.0.0.0",
            product_version="1.0.0.0",
        )
        values.update(changes)
        return BuildConfig(**values)

    def test_generates_native_windows_and_linux_jobs(self):
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        workflow = generate_cross_build_workflow(
            self.config(root),
            project_root=str(root),
            windows_icon=str(root / "assets" / "icon.ico"),
            linux_icon=str(root / "assets" / "icon.png"),
        )
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn('cache: "pip"', workflow)
        self.assertIn("timeout-minutes: 120", workflow)
        self.assertIn("retention-days: 14", workflow)
        self.assertIn('PYTHONUNBUFFERED: "1"', workflow)
        self.assertNotIn("  push:", workflow)


    def test_skips_pip_cache_when_requirements_file_is_absent(self):
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "requirements.txt").unlink()
        workflow = generate_cross_build_workflow(
            self.config(root), project_root=str(root), targets=("windows",)
        )
        self.assertNotIn('cache: "pip"', workflow)
        self.assertIn('REQUIREMENTS_FILE: "requirements.txt"', workflow)

    def test_can_enable_push_trigger(self):
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        workflow = generate_cross_build_workflow(
            self.config(root), project_root=str(root), targets=("windows",), build_on_push=True
        )
        self.assertIn("  push:", workflow)
        self.assertNotIn("runs-on: ubuntu-latest", workflow)

    def test_rewrites_resources_to_repository_relative_paths(self):
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        config = self.config(
            root,
            data_mappings=[DataMapping(str(root / "assets"), "assets", "dir")],
        )
        workflow = generate_cross_build_workflow(config, project_root=str(root), targets=("windows",))
        self.assertNotIn(str(root), workflow)

    def test_rejects_entry_script_outside_project_root(self):
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        other = Path(tempfile.mkdtemp()) / "other.py"
        other.write_text("print(1)", encoding="utf-8")
        self.addCleanup(lambda: other.parent.exists() and __import__("shutil").rmtree(other.parent))
        with self.assertRaises(CrossBuildError):
            generate_cross_build_workflow(
                self.config(root, entry_script=str(other)), project_root=str(root)
            )

    def test_writes_workflow_to_github_folder(self):
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        path = write_cross_build_workflow("name: test\n", str(root))
        self.assertEqual(path.name, "nuitka-studio-cross-build.yml")
        self.assertEqual(path.read_text(encoding="utf-8"), "name: test\n")

    def test_detects_entry_script_for_a_new_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app.py").write_text("print('app')\n", encoding="utf-8")
            (root / "helper.py").write_text("print('helper')\n", encoding="utf-8")
            self.assertEqual(detect_project_entry_script(root), root / "app.py")

    def test_entry_discovery_ignores_virtual_environment_scripts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".venv").mkdir()
            (root / ".venv" / "main.py").write_text("print('wrong')\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('right')\n", encoding="utf-8")
            self.assertEqual(detect_project_entry_script(root), root / "src" / "main.py")

    def test_path_inside_project_rejects_previous_application(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            swiftshare = base / "SwiftShare"
            nexaconvert = base / "NexaConvert"
            swiftshare.mkdir()
            nexaconvert.mkdir()
            script = nexaconvert / "main.py"
            script.write_text("print('old')\n", encoding="utf-8")
            self.assertFalse(path_is_inside_project(str(script), str(swiftshare)))
            self.assertTrue(path_is_inside_project(str(swiftshare / "main.py"), str(swiftshare)))


if __name__ == "__main__":
    unittest.main()
