# SPDX-License-Identifier: MIT
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


# The lifecycle helpers can be tested without opening a graphical display. The
# real dependencies are used when available; lightweight import stubs keep the
# tests runnable in minimal CI environments too.
try:
    import customtkinter  # noqa: F401
except ImportError:
    customtkinter = types.ModuleType("customtkinter")
    customtkinter.CTk = object
    sys.modules["customtkinter"] = customtkinter

try:
    from PIL import Image  # noqa: F401
except ImportError:
    pil = types.ModuleType("PIL")
    pil.Image = types.SimpleNamespace()
    sys.modules["PIL"] = pil


app_module = importlib.import_module("nuitka_gui.app")


class FakeWidget:
    def __init__(self):
        self.grid_calls = 0
        self.grid_remove_calls = 0
        self.configurations = []

    def grid(self, *args, **kwargs):
        self.grid_calls += 1

    def grid_remove(self):
        self.grid_remove_calls += 1

    def configure(self, **kwargs):
        self.configurations.append(kwargs)


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class LifecycleTests(unittest.TestCase):
    def test_saved_theme_is_read_before_widget_construction(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"appearance_mode": "dark"}), encoding="utf-8")
            with mock.patch.object(app_module, "settings_path", return_value=path):
                self.assertEqual(app_module.load_saved_appearance_mode(), "dark")

    def test_settings_signature_is_key_order_independent(self):
        left = {"b": [2, 3], "a": 1}
        right = {"a": 1, "b": [2, 3]}
        self.assertEqual(app_module.settings_signature(left), app_module.settings_signature(right))

    def test_startup_builds_only_the_build_page(self):
        application = object.__new__(app_module.NuitkaStudioApp)
        application.pages = {}
        method_to_page = {
            "_build_build_page": "Build",
            "_build_cross_build_page": "Cross Build",
            "_build_packages_page": "Packages",
            "_build_resources_page": "Resources",
            "_build_identity_page": "App Identity",
            "_build_installer_page": "Installer",
            "_build_history_page": "History",
            "_build_settings_page": "Settings",
            "_build_help_page": "How to Use",
            "_build_donate_page": "Donate",
        }
        for method_name, page_name in method_to_page.items():
            setattr(
                application,
                method_name,
                lambda selected=page_name: application.pages.__setitem__(selected, FakeWidget()),
            )

        application._build_pages()

        self.assertEqual(set(application.pages), {"Build"})
        self.assertEqual(set(application._page_builders), set(method_to_page.values()))

    def test_navigation_creates_a_page_once_and_hides_only_previous_page(self):
        application = object.__new__(app_module.NuitkaStudioApp)
        build_page = FakeWidget()
        package_page = FakeWidget()
        build_count = 0

        def build_packages():
            nonlocal build_count
            build_count += 1
            application.pages["Packages"] = package_page

        application.pages = {"Build": build_page}
        application._page_builders = {"Packages": build_packages}
        application.active_page = "Build"
        application.page_title = FakeWidget()
        application.page_subtitle = FakeWidget()
        application.nav_buttons = {"Build": FakeWidget(), "Packages": FakeWidget()}
        application.action_bar = FakeWidget()
        application.target_os = "linux"

        application._show_page("Packages")
        application._show_page("Packages")

        self.assertEqual(build_count, 1)
        self.assertEqual(build_page.grid_remove_calls, 1)
        self.assertEqual(package_page.grid_calls, 2)
        self.assertEqual(application.action_bar.grid_remove_calls, 2)

    def test_unchanged_settings_do_not_write_to_disk(self):
        application = object.__new__(app_module.NuitkaStudioApp)
        data = {"settings_schema": 9, "application_name": "NexaConvert"}
        application._settings_dict = lambda: data
        application._last_saved_settings_signature = app_module.settings_signature(data)
        application.logger = mock.Mock()

        with mock.patch.object(app_module, "atomic_write_json") as writer:
            self.assertTrue(application._save_settings())
            writer.assert_not_called()

    def test_lazy_text_value_uses_cache_until_page_exists(self):
        application = object.__new__(app_module.NuitkaStudioApp)
        self.assertEqual(
            application._text_lines_or_cached("missing_textbox", ["fitz", "pillow_heif"]),
            ["fitz", "pillow_heif"],
        )

    def test_cross_build_switches_away_from_previous_application_entry_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            old_root = base / "NexaConvert"
            new_root = base / "SwiftShare"
            old_root.mkdir()
            new_root.mkdir()
            old_script = old_root / "main.py"
            new_script = new_root / "main.py"
            old_script.write_text("print('old')\n", encoding="utf-8")
            new_script.write_text("print('new')\n", encoding="utf-8")

            application = object.__new__(app_module.NuitkaStudioApp)
            application.cross_project_root_var = FakeVar(str(new_root))
            application.script_var = FakeVar(str(old_script))
            application.output_dir_var = FakeVar(str(old_root / "dist"))
            application.application_name_var = FakeVar("NexaConvert")
            application.output_name_var = FakeVar("NexaConvert.exe")
            application.product_var = FakeVar("NexaConvert")
            application.package_id_var = FakeVar("nexaconvert")
            application.target_os = "linux"
            application.icon_var = FakeVar(str(old_root / "icon.ico"))
            application.cross_windows_icon_var = FakeVar(str(old_root / "icon.ico"))
            application.cross_linux_icon_var = FakeVar("")
            application.installer_license_var = FakeVar("")
            application.cross_status_var = FakeVar("")
            application.data_mappings = []
            application._cross_workflow_path = Path("old.yml")
            application._schedule_refresh = lambda *_args, **_kwargs: None
            application._refresh_data_list = lambda **_kwargs: None

            application._ensure_cross_project_consistency()

            self.assertEqual(Path(application.script_var.get()), new_script)
            self.assertEqual(Path(application.output_dir_var.get()), new_root / "dist")
            self.assertEqual(application.application_name_var.get(), "SwiftShare")
            self.assertEqual(application.output_name_var.get(), "SwiftShare")
            self.assertEqual(application.product_var.get(), "SwiftShare")
            self.assertEqual(application.package_id_var.get(), "swiftshare")
            self.assertEqual(application.icon_var.get(), "")
            self.assertIsNone(application._cross_workflow_path)


if __name__ == "__main__":
    unittest.main()
