# SPDX-License-Identifier: MIT
"""Build a rootless Debian package around a completed Nuitka Linux build."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile


PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")


class DebianPackagingError(RuntimeError):
    """Raised when a native Linux build cannot be packaged as a .deb file."""


@dataclass(frozen=True)
class DebianPackageConfig:
    executable: Path
    output_directory: Path
    package_id: str
    application_name: str
    version: str
    maintainer: str
    description: str = "Compiled Python application"
    section: str = "utils"
    icon_path: Path | None = None
    mode: str = "standalone"


def debian_architecture() -> str:
    """Return the architecture spelling expected by Debian packages."""
    dpkg = shutil.which("dpkg")
    if dpkg:
        try:
            result = subprocess.run(
                [dpkg, "--print-architecture"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            if result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    machine = platform.machine().lower()
    return {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv7l": "armhf",
        "armv7": "armhf",
        "i386": "i386",
        "i686": "i386",
    }.get(machine, machine or "all")


def _single_line(value: str, fallback: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split()).strip() or fallback


def _installed_size(root: Path) -> int:
    total = sum(path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    return max(1, (total + 1023) // 1024)


def _copy_application(config: DebianPackageConfig, root: Path) -> Path:
    destination = root / "opt" / config.package_id
    destination.mkdir(parents=True)
    if config.mode == "standalone" and config.executable.parent.name.endswith(".dist"):
        shutil.copytree(config.executable.parent, destination, dirs_exist_ok=True, symlinks=True)
    else:
        shutil.copy2(config.executable, destination / config.executable.name)
    installed_executable = destination / config.executable.name
    installed_executable.chmod(installed_executable.stat().st_mode | 0o111)
    return installed_executable


def _write_desktop_entry(config: DebianPackageConfig, root: Path) -> None:
    applications = root / "usr" / "share" / "applications"
    applications.mkdir(parents=True)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={_single_line(config.application_name, config.package_id)}",
        f"Comment={_single_line(config.description, 'Compiled Python application')}",
        f"Exec=/usr/bin/{config.package_id}",
        "Terminal=false",
        "Categories=Utility;",
    ]
    if config.icon_path is not None and config.icon_path.is_file():
        suffix = config.icon_path.suffix.lower()
        if suffix == ".svg":
            icon_dir = root / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        elif suffix == ".xpm":
            icon_dir = root / "usr" / "share" / "pixmaps"
        else:
            icon_dir = root / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
        icon_dir.mkdir(parents=True)
        shutil.copy2(config.icon_path, icon_dir / f"{config.package_id}{suffix}")
        lines.insert(-1, f"Icon={config.package_id}")
    (applications / f"{config.package_id}.desktop").write_text("\n".join((*lines, "")), encoding="utf-8")


def build_debian_package(config: DebianPackageConfig) -> Path:
    """Create and return an installable .deb using the system dpkg-deb tool."""
    if os.name == "nt" or not platform.system().lower().startswith("linux"):
        raise DebianPackagingError("Debian packages can only be created on a Linux host.")
    if not PACKAGE_RE.fullmatch(config.package_id):
        raise DebianPackagingError("The Debian package ID is invalid.")
    if not config.executable.is_file():
        raise DebianPackagingError(f"The compiled Linux executable was not found: {config.executable}")
    if config.mode not in {"standalone", "onefile"}:
        raise DebianPackagingError("The build mode must be standalone or onefile.")
    dpkg_deb = shutil.which("dpkg-deb")
    if not dpkg_deb:
        raise DebianPackagingError("dpkg-deb is missing. Install the dpkg package, then build again.")

    version = _single_line(config.version, "1.0.0.0")
    architecture = debian_architecture()
    output = config.output_directory / f"{config.package_id}_{version}_{architecture}.deb"
    config.output_directory.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"{config.package_id}-deb-") as temporary:
        root = Path(temporary) / "package"
        control_dir = root / "DEBIAN"
        control_dir.mkdir(parents=True)
        installed_executable = _copy_application(config, root)

        bin_dir = root / "usr" / "bin"
        bin_dir.mkdir(parents=True)
        os.symlink(f"/opt/{config.package_id}/{installed_executable.name}", bin_dir / config.package_id)
        _write_desktop_entry(config, root)

        control = (
            f"Package: {config.package_id}\n"
            f"Version: {version}\n"
            f"Section: {_single_line(config.section, 'utils')}\n"
            "Priority: optional\n"
            f"Architecture: {architecture}\n"
            f"Maintainer: {_single_line(config.maintainer, 'Unknown maintainer')}\n"
            f"Installed-Size: {_installed_size(root)}\n"
            f"Description: {_single_line(config.description, config.application_name)}\n"
        )
        (control_dir / "control").write_text(control, encoding="utf-8")
        try:
            result = subprocess.run(
                [dpkg_deb, "--root-owner-group", "--build", str(root), str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise DebianPackagingError(f"Could not start dpkg-deb: {exc}") from exc
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            raise DebianPackagingError(f"dpkg-deb failed: {details or 'unknown error'}")

    if not output.is_file():
        raise DebianPackagingError("dpkg-deb reported success but did not create the package.")
    return output
