# SPDX-License-Identifier: MIT
import unittest

from nuitka_gui.command_builder import BuildConfig, ConfigurationError, DataMapping, build_command


class CommandBuilderTests(unittest.TestCase):
    def base(self, **changes):
        values = dict(
            python_executable=r"C:\Python312\python.exe",
            entry_script=r"C:\Project Folder\main.py",
            output_directory=r"C:\Project Folder\dist",
            output_filename="Demo.exe",
        )
        values.update(changes)
        return BuildConfig(**values)

    def test_builds_arguments_without_shell_string_concatenation(self):
        command = build_command(self.base(), require_paths=False)
        self.assertEqual(command[:3], [r"C:\Python312\python.exe", "-m", "nuitka"])
        self.assertIn("--mode=standalone", command)
        self.assertIn("--windows-console-mode=disable", command)
        self.assertEqual(command[-1], r"C:\Project Folder\main.py")

    def test_onefile_metadata_and_data(self):
        config = self.base(
            mode="onefile",
            company_name="Demo Company",
            file_version="1.2.3.4",
            packages=["fitz"],
            data_mappings=[DataMapping(r"C:\Project Folder\assets", "assets", "dir")],
        )
        command = build_command(config, require_paths=False)
        self.assertIn("--mode=onefile", command)
        self.assertIn("--company-name=Demo Company", command)
        self.assertIn("--include-package=fitz", command)
        self.assertIn(r"--include-data-dir=C:\Project Folder\assets=assets", command)

    def test_application_name_becomes_default_product_name(self):
        command = build_command(self.base(application_name="NexaConvert"), require_paths=False)
        self.assertIn("--product-name=NexaConvert", command)

    def test_linux_build_uses_native_options_and_filename(self):
        command = build_command(
            self.base(
                target_os="linux",
                console_mode="native",
                compiler="gcc",
                output_filename="NexaConvert.exe",
                icon_path="",
            ),
            require_paths=False,
        )
        self.assertIn("--output-filename=NexaConvert", command)
        self.assertNotIn("--windows-console-mode=disable", command)
        self.assertFalse(any(option.startswith("--product-name=") for option in command))

    def test_linux_clang_option(self):
        command = build_command(
            self.base(target_os="linux", console_mode="native", compiler="clang"),
            require_paths=False,
        )
        self.assertIn("--clang", command)

    def test_linux_accepts_debian_package_output(self):
        command = build_command(
            self.base(
                target_os="linux",
                console_mode="native",
                compiler="auto",
                package_format="deb",
                package_id="nexa-convert",
                package_maintainer="John Edward Dela Cruz",
            ),
            require_paths=False,
        )
        self.assertIn("--mode=standalone", command)

    def test_windows_accepts_setup_installer_output(self):
        command = build_command(
            self.base(
                package_format="setup",
                installer_publisher="John Edward Dela Cruz",
                installer_website="https://myportfoliohub.online",
            ),
            require_paths=False,
        )
        self.assertIn("--mode=standalone", command)

    def test_windows_setup_requires_publisher(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(package_format="setup", installer_publisher=""), require_paths=False)

    def test_windows_rejects_debian_package_output(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(package_format="deb"), require_paths=False)

    def test_debian_package_id_must_be_policy_compatible(self):
        with self.assertRaises(ConfigurationError):
            build_command(
                self.base(
                    target_os="linux",
                    console_mode="native",
                    compiler="auto",
                    package_format="deb",
                    package_id="Nexa Convert",
                ),
                require_paths=False,
            )

    def test_linux_rejects_windows_compiler(self):
        with self.assertRaises(ConfigurationError):
            build_command(
                self.base(target_os="linux", console_mode="native", compiler="msvc"),
                require_paths=False,
            )

    def test_rejects_non_ico_icon(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(icon_path=r"C:\icon.png"), require_paths=False)

    def test_rejects_three_part_version(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(file_version="1.2.3"), require_paths=False)

    def test_adds_exe_extension(self):
        command = build_command(self.base(output_filename="Demo"), require_paths=False)
        self.assertIn("--output-filename=Demo.exe", command)

    def test_fast_build_options(self):
        command = build_command(
            self.base(mode="onefile", jobs="-2", onefile_no_compression=True),
            require_paths=False,
        )
        self.assertIn("--jobs=-2", command)
        self.assertIn("--onefile-no-compression", command)

    def test_no_compression_is_ignored_for_standalone(self):
        command = build_command(
            self.base(mode="standalone", onefile_no_compression=True),
            require_paths=False,
        )
        self.assertNotIn("--onefile-no-compression", command)

    def test_rejects_zero_jobs(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(jobs="0"), require_paths=False)

    def test_rejects_reserved_windows_filename(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(output_filename="CON.exe"), require_paths=False)

    def test_rejects_resource_parent_traversal(self):
        with self.assertRaises(ConfigurationError):
            build_command(
                self.base(data_mappings=[DataMapping(r"C:\Project\secret", "../secret", "dir")]),
                require_paths=False,
            )

    def test_rejects_absolute_resource_destination(self):
        with self.assertRaises(ConfigurationError):
            build_command(
                self.base(data_mappings=[DataMapping(r"C:\Project\assets", r"C:\output", "dir")]),
                require_paths=False,
            )

    def test_rejects_gui_controlled_advanced_option(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(extra_arguments=["--output-dir=other"]), require_paths=False)

    def test_allows_safe_advanced_option(self):
        command = build_command(
            self.base(extra_arguments=["--nofollow-import-to=tests"]),
            require_paths=False,
        )
        self.assertIn("--nofollow-import-to=tests", command)

    def test_allows_repeatable_plugin_advanced_option(self):
        command = build_command(
            self.base(extra_arguments=["--enable-plugin=pyside6"]),
            require_paths=False,
        )
        self.assertIn("--enable-plugin=pyside6", command)

    def test_rejects_invalid_package_name(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(packages=["bad package"]), require_paths=False)

    def test_rejects_oversized_version_component(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(file_version="1.0.0.65536"), require_paths=False)

    def test_rejects_metadata_line_break(self):
        with self.assertRaises(ConfigurationError):
            build_command(self.base(company_name="Bad\nCompany"), require_paths=False)


if __name__ == "__main__":
    unittest.main()
