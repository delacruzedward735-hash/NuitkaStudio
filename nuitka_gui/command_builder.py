# SPDX-License-Identifier: MIT
"""Validation and command generation for the Nuitka GUI.

This module intentionally has no GUI imports so the important command-building
logic can be tested without opening a window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
from typing import Iterable


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
PACKAGE_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
DEBIAN_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
CONTROLLED_ADVANCED_OPTIONS = {
    "--mode",
    "--standalone",
    "--onefile",
    "--output-dir",
    "--output-filename",
    "--windows-console-mode",
    "--windows-icon-from-ico",
    "--jobs",
    "--msvc",
    "--mingw64",
    "--clang",
    "--remove-output",
    "--show-progress",
    "--assume-yes-for-downloads",
    "--onefile-no-compression",
    "--main",
    "--company-name",
    "--product-name",
    "--file-description",
    "--file-version",
    "--product-version",
    "--copyright",
}


class ConfigurationError(ValueError):
    """Raised when a build configuration is incomplete or invalid."""


@dataclass
class DataMapping:
    source: str
    destination: str
    kind: str = "dir"  # "dir" or "file"


@dataclass
class BuildConfig:
    python_executable: str
    entry_script: str
    output_directory: str
    output_filename: str = "Application.exe"
    application_name: str = "Application"
    target_os: str = "windows"
    package_format: str = "native"
    package_id: str = "application"
    package_maintainer: str = "John Edward Dela Cruz"
    package_section: str = "utils"
    mode: str = "standalone"
    console_mode: str = "disable"
    icon_path: str = ""
    compiler: str = "auto"
    enable_tk_plugin: bool = True
    include_customtkinter_data: bool = False
    assume_downloads: bool = True
    remove_output: bool = True
    show_progress: bool = True
    jobs: str = "auto"
    onefile_no_compression: bool = False
    packages: list[str] = field(default_factory=list)
    package_data: list[str] = field(default_factory=list)
    data_mappings: list[DataMapping] = field(default_factory=list)
    extra_arguments: list[str] = field(default_factory=list)
    company_name: str = ""
    product_name: str = ""
    file_description: str = ""
    file_version: str = ""
    product_version: str = ""
    copyright_text: str = ""
    installer_publisher: str = "John Edward Dela Cruz"
    installer_website: str = ""
    installer_scope: str = "all_users"
    installer_compiler: str = ""
    installer_license: str = ""
    installer_desktop_shortcut: bool = True
    installer_start_menu_shortcut: bool = True
    installer_launch_after_install: bool = True


def clean_lines(value: str | Iterable[str]) -> list[str]:
    """Convert newline-separated input to unique, non-empty values."""
    lines = value.splitlines() if isinstance(value, str) else value
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        item = str(line).strip()
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _reject_line_breaks(label: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ConfigurationError(f"{label} cannot contain a line break.")


def _validate_destination(destination: str) -> None:
    normalized = destination.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ConfigurationError("Resource destinations must be relative paths inside the application.")
    raw_parts = normalized.split("/")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise ConfigurationError("Resource destinations cannot be empty or contain . or .. path segments.")


def _validate_advanced_arguments(arguments: Iterable[str]) -> None:
    for argument in clean_lines(arguments):
        _reject_line_breaks("Advanced arguments", argument)
        if not argument.startswith("--"):
            raise ConfigurationError("Every advanced argument must begin with --.")
        option_name = argument.split("=", 1)[0]
        if any(char.isspace() for char in option_name):
            raise ConfigurationError("Use one complete advanced argument per line, preferably --option=value.")
        if option_name in CONTROLLED_ADVANCED_OPTIONS:
            raise ConfigurationError(f"{option_name} is controlled by the interface and cannot be duplicated under Advanced arguments.")


def validate_config(config: BuildConfig, *, require_paths: bool = True) -> None:
    for label, value in (
        ("Python interpreter", config.python_executable),
        ("Entry script", config.entry_script),
        ("Output directory", config.output_directory),
        ("Output filename", config.output_filename),
        ("Application name", config.application_name),
        ("Icon path", config.icon_path),
        ("Debian package ID", config.package_id),
        ("Debian maintainer", config.package_maintainer),
        ("Debian section", config.package_section),
        ("Installer publisher", config.installer_publisher),
        ("Installer website", config.installer_website),
        ("Inno Setup compiler", config.installer_compiler),
        ("Installer license", config.installer_license),
    ):
        _reject_line_breaks(label, value)

    if not config.python_executable.strip():
        raise ConfigurationError("Select a Python interpreter.")
    if require_paths and not Path(config.python_executable).is_file():
        raise ConfigurationError("The selected Python interpreter does not exist.")

    if not config.entry_script.strip():
        raise ConfigurationError("Select the main Python script to compile.")
    script = Path(config.entry_script)
    if script.suffix.lower() not in {".py", ".pyw"}:
        raise ConfigurationError("The entry file must be a .py or .pyw file.")
    if require_paths and not script.is_file():
        raise ConfigurationError("The selected entry script does not exist.")

    if config.mode not in {"standalone", "onefile"}:
        raise ConfigurationError("Build mode must be standalone or onefile.")
    if config.target_os not in {"windows", "linux"}:
        raise ConfigurationError("Build target must be Windows or Linux.")
    if config.target_os == "windows":
        if config.package_format not in {"native", "exe", "setup"}:
            raise ConfigurationError("Windows output format must be a Windows EXE or Setup Installer.")
        if config.console_mode not in {"disable", "force", "attach", "hide"}:
            raise ConfigurationError("Select a valid Windows console mode.")
        if config.compiler not in {"auto", "msvc", "mingw64"}:
            raise ConfigurationError("Select a valid Windows compiler toolchain.")
    elif config.console_mode != "native":
        raise ConfigurationError("Linux console behavior must use the native mode.")
    elif config.compiler not in {"auto", "gcc", "clang"}:
        raise ConfigurationError("Select Auto, GCC, or Clang for Linux.")
    elif config.package_format not in {"native", "elf", "deb"}:
        raise ConfigurationError("Linux output format must be an ELF executable or Debian package.")

    if config.package_format == "setup":
        if any(character in config.application_name for character in '<>:"/\\|?*'):
            raise ConfigurationError("Windows installer application name contains a character that cannot be used in an installation folder.")
        if not config.installer_publisher.strip():
            raise ConfigurationError("Enter a publisher name for the Windows installer.")
        if config.installer_scope not in {"all_users", "current_user"}:
            raise ConfigurationError("Select a valid Windows installer scope.")
        if config.installer_website and not re.match(r"^https?://", config.installer_website, re.IGNORECASE):
            raise ConfigurationError("Installer website must begin with http:// or https://.")
        if require_paths and config.installer_compiler and not Path(config.installer_compiler).is_file():
            raise ConfigurationError("The selected Inno Setup compiler does not exist.")
        if require_paths and config.installer_license and not Path(config.installer_license).is_file():
            raise ConfigurationError("The selected installer license file does not exist.")

    if config.package_format == "deb":
        if not DEBIAN_PACKAGE_RE.fullmatch(config.package_id):
            raise ConfigurationError(
                "Debian package ID must be lowercase and use only letters, numbers, +, . or -."
            )
        if not config.package_maintainer.strip():
            raise ConfigurationError("Enter a maintainer name for the Debian package.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", config.package_section):
            raise ConfigurationError("Enter a valid lowercase Debian package section, such as utils.")
    if config.jobs != "auto":
        if not re.fullmatch(r"-?\d+", config.jobs):
            raise ConfigurationError("Compilation jobs must be Auto or a whole number.")
        try:
            jobs = int(config.jobs)
        except ValueError as exc:
            raise ConfigurationError("Compilation jobs must be Auto or a whole number.") from exc
        if jobs == 0 or jobs < -64 or jobs > 256:
            raise ConfigurationError("Compilation jobs must be between -64 and 256, excluding zero.")

    if not config.output_directory.strip():
        raise ConfigurationError("Select an output directory.")
    if not config.application_name.strip():
        raise ConfigurationError("Enter an application name.")
    if len(config.application_name) > 128:
        raise ConfigurationError("The application name is too long (maximum 128 characters).")
    if not config.output_filename.strip():
        raise ConfigurationError("Enter an output filename.")
    invalid_filename_chars = '<>:"/\\|?*' if config.target_os == "windows" else "/\x00"
    if any(char in config.output_filename for char in invalid_filename_chars):
        raise ConfigurationError(f"The output filename contains a character that is invalid on {config.target_os.title()}.")
    if config.output_filename.endswith((" ", ".")):
        raise ConfigurationError("The output filename cannot end with a space or period.")
    output_stem = Path(config.output_filename).stem
    if not output_stem.strip(" .") or output_stem.endswith((" ", ".")):
        raise ConfigurationError("Enter a valid executable filename.")
    device_stem = config.output_filename.split(".", 1)[0].upper().rstrip(" .")
    if config.target_os == "windows" and device_stem in WINDOWS_RESERVED_NAMES:
        raise ConfigurationError("The output filename is reserved by Windows. Choose another name.")

    if config.icon_path:
        icon = Path(config.icon_path)
        if config.target_os == "windows" and icon.suffix.lower() != ".ico":
            raise ConfigurationError("Windows application icons must use the .ico format.")
        if config.target_os == "linux" and icon.suffix.lower() not in {".png", ".svg", ".xpm"}:
            raise ConfigurationError("Linux launcher icons must use PNG, SVG, or XPM format.")
        if require_paths and not icon.is_file():
            raise ConfigurationError("The selected icon does not exist.")

    for label, version in (
        ("File version", config.file_version),
        ("Product version", config.product_version),
    ):
        _reject_line_breaks(label, version)
        if version:
            if not VERSION_RE.fullmatch(version):
                raise ConfigurationError(f"{label} must contain four numbers, for example 1.0.0.0.")
            if any(int(part) > 65535 for part in version.split(".")):
                raise ConfigurationError(f"Every {label.lower()} component must be between 0 and 65535.")

    for label, value in (
        ("Company name", config.company_name),
        ("Product name", config.product_name),
        ("File description", config.file_description),
        ("Copyright", config.copyright_text),
    ):
        _reject_line_breaks(label, value)
        if len(value) > 512:
            raise ConfigurationError(f"{label} is too long (maximum 512 characters).")

    for package in (*clean_lines(config.packages), *clean_lines(config.package_data)):
        if not PACKAGE_RE.fullmatch(package):
            raise ConfigurationError(f"Invalid Python package name: {package}")

    for mapping in config.data_mappings:
        if mapping.kind not in {"dir", "file"}:
            raise ConfigurationError("A data mapping has an invalid type.")
        if not mapping.source or not mapping.destination:
            raise ConfigurationError("Every data mapping needs a source and destination.")
        if "=" in mapping.source or "=" in mapping.destination:
            raise ConfigurationError("Data mapping paths cannot contain an equals sign (=).")
        _reject_line_breaks("Data source", mapping.source)
        _reject_line_breaks("Data destination", mapping.destination)
        _validate_destination(mapping.destination)
        if require_paths:
            source = Path(mapping.source)
            valid = source.is_dir() if mapping.kind == "dir" else source.is_file()
            if not valid:
                raise ConfigurationError(f"Data source does not exist: {mapping.source}")

    _validate_advanced_arguments(config.extra_arguments)


def build_command(config: BuildConfig, *, require_paths: bool = True) -> list[str]:
    """Return a subprocess-safe Nuitka command argument list."""
    validate_config(config, require_paths=require_paths)

    command = [config.python_executable, "-m", "nuitka"]
    command.append(f"--mode={config.mode}")

    if config.assume_downloads:
        command.append("--assume-yes-for-downloads")
    if config.remove_output:
        command.append("--remove-output")
    if config.show_progress:
        command.append("--show-progress")
    if config.jobs != "auto":
        command.append(f"--jobs={config.jobs}")
    if config.mode == "onefile" and config.onefile_no_compression:
        command.append("--onefile-no-compression")

    if config.target_os == "windows":
        command.append(f"--windows-console-mode={config.console_mode}")
        if config.icon_path:
            command.append(f"--windows-icon-from-ico={config.icon_path}")
        if config.compiler == "msvc":
            command.append("--msvc=latest")
        elif config.compiler == "mingw64":
            command.append("--mingw64")
    elif config.compiler == "clang":
        command.append("--clang")

    if config.enable_tk_plugin:
        command.append("--enable-plugin=tk-inter")
    if config.include_customtkinter_data:
        command.append("--include-package-data=customtkinter")

    for package in clean_lines(config.packages):
        command.append(f"--include-package={package}")
    for package in clean_lines(config.package_data):
        command.append(f"--include-package-data={package}")
    for mapping in config.data_mappings:
        option = "--include-data-dir" if mapping.kind == "dir" else "--include-data-files"
        command.append(f"{option}={mapping.source}={mapping.destination}")

    metadata = (
        ("company-name", config.company_name),
        ("product-name", config.product_name.strip() or config.application_name.strip()),
        ("file-description", config.file_description),
        ("file-version", config.file_version),
        ("product-version", config.product_version),
        ("copyright", config.copyright_text),
    )
    if config.target_os == "windows":
        for option, value in metadata:
            if value.strip():
                command.append(f"--{option}={value.strip()}")

    output_name = normalized_output_filename(config)
    command.extend(
        [
            f"--output-dir={config.output_directory}",
            f"--output-filename={output_name}",
        ]
    )
    command.extend(config.extra_arguments)
    command.append(config.entry_script)
    return command


def normalized_output_filename(config: BuildConfig) -> str:
    """Return a native output filename for the selected host target."""
    output_name = config.output_filename.strip()
    if config.target_os == "windows" and not output_name.lower().endswith(".exe"):
        output_name += ".exe"
    if config.target_os == "linux" and output_name.lower().endswith(".exe"):
        output_name = output_name[:-4]
    return output_name


def display_command(command: list[str], target_os: str | None = None) -> str:
    """Format an argument list for the native command shell."""
    target = target_os or ("windows" if sys.platform == "win32" else "linux")
    return subprocess.list2cmdline(command) if target == "windows" else shlex.join(command)
