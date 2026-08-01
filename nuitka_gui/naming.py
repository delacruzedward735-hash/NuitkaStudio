# SPDX-License-Identifier: MIT
"""Application-name helpers shared by the UI and tests."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
import re


GENERIC_ENTRY_NAMES = {"__main__", "app", "main", "run", "wsgi"}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def infer_application_name(entry_script: Path) -> str:
    """Choose a useful initial name without forcing generic main.py/app.py."""
    raw_path = str(entry_script)
    parsed = PureWindowsPath(raw_path) if "\\" in raw_path else Path(raw_path)
    stem = parsed.stem.strip()
    candidate = parsed.parent.name if stem.lower() in GENERIC_ENTRY_NAMES else stem
    candidate = candidate.replace("_", " ").strip(" .")
    return candidate or "Application"


def executable_name(application_name: str, target_os: str = "windows") -> str:
    """Create a safe native executable filename from a friendly app name."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", application_name.strip())
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = "Application"
    if target_os == "windows" and value.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        value += " App"
    if target_os == "windows" and not value.lower().endswith(".exe"):
        value += ".exe"
    elif target_os == "linux" and value.lower().endswith(".exe"):
        value = value[:-4]
    return value


def debian_package_id(application_name: str) -> str:
    """Create a policy-compatible Debian package name from a friendly name."""
    value = application_name.strip().lower()
    value = re.sub(r"[^a-z0-9+.-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-.+")
    if not value:
        value = "application"
    if not value[0].isalnum():
        value = "app-" + value
    if len(value) < 2:
        value = "app-" + value
    return value[:100].rstrip("-.+") or "application"
