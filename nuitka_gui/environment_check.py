# SPDX-License-Identifier: MIT
"""Reliable, low-overhead checks for a selected project Python environment."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any


_PROBE_SCRIPT = r'''
import importlib.util
import json
import sys

result = {
    "version": "Python " + ".".join(map(str, sys.version_info[:3])),
    "version_info": list(sys.version_info[:3]),
    "nuitka_installed": False,
    "nuitka_version": "",
    "nuitka_issue": "",
}

try:
    result["nuitka_installed"] = importlib.util.find_spec("nuitka") is not None
except Exception as exc:
    result["nuitka_issue"] = f"Nuitka installation could not be inspected: {exc}"

if result["nuitka_installed"]:
    try:
        from importlib.metadata import version
        result["nuitka_version"] = version("Nuitka")
    except Exception as exc:
        result["nuitka_issue"] = str(exc) or "Nuitka package metadata could not be read."

print(json.dumps(result, ensure_ascii=False))
'''

_VERSION_RE = re.compile(r"(?:Python\s+)?(\d+)\.(\d+)(?:\.(\d+))?")


def parse_python_version(value: object) -> tuple[int, int, int]:
    """Return a safe ``(major, minor, micro)`` tuple from probe data or text."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            major = int(value[0])
            minor = int(value[1])
            micro = int(value[2]) if len(value) >= 3 else 0
            return major, minor, micro
        except (TypeError, ValueError):
            pass
    match = _VERSION_RE.search(str(value or ""))
    if not match:
        return 0, 0, 0
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _decode_probe(stdout: str) -> dict[str, Any]:
    """Decode the final JSON line while tolerating harmless interpreter output."""
    for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("The selected Python interpreter did not return valid setup information.")


def check_python_environment(python: str) -> dict[str, object]:
    """Check Python and Nuitka in one interpreter process.

    Older releases launched three short-lived Python processes for every setup
    check. One JSON probe is substantially faster on Windows and keeps startup
    checks lightweight on Linux.
    """
    result: dict[str, object] = {
        "python": False,
        "version": "",
        "version_info": [0, 0, 0],
        "nuitka": False,
        "nuitka_installed": False,
        "nuitka_version": "",
        "nuitka_issue": "",
    }
    try:
        completed = subprocess.run(
            [python, "-c", _PROBE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired:
        result["nuitka_issue"] = "The selected Python interpreter did not respond within 25 seconds."
        return result
    except (OSError, subprocess.SubprocessError) as exc:
        result["nuitka_issue"] = f"Python could not start: {exc}"
        return result

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "The selected Python interpreter failed.").strip()
        result["nuitka_issue"] = detail.splitlines()[-1] if detail else "The selected Python interpreter failed."
        return result

    try:
        probe = _decode_probe(completed.stdout or "")
    except (ValueError, TypeError) as exc:
        result["nuitka_issue"] = str(exc)
        return result

    version = str(probe.get("version", "")).strip()
    version_info = parse_python_version(probe.get("version_info") or version)
    installed = bool(probe.get("nuitka_installed"))
    nuitka_version = str(probe.get("nuitka_version", "")).strip()
    issue = str(probe.get("nuitka_issue", "")).strip()

    result.update(
        {
            "python": version_info[:2] != (0, 0),
            "version": version or (f"Python {version_info[0]}.{version_info[1]}.{version_info[2]}" if version_info[:2] != (0, 0) else ""),
            "version_info": list(version_info),
            "nuitka_installed": installed,
            "nuitka_version": nuitka_version,
            "nuitka": installed and bool(nuitka_version) and not issue,
            "nuitka_issue": issue,
        }
    )
    if result["python"] and not installed and not issue:
        result["nuitka_issue"] = "Nuitka is not installed in this selected Python environment."
    elif installed and not result["nuitka"] and not issue:
        result["nuitka_issue"] = "Nuitka is installed, but its package metadata could not be read."
    return result


def nuitka_install_command(python: str) -> list[str]:
    """Return the repair/install command for the exact selected interpreter."""
    return [
        python,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "nuitka",
        "ordered-set",
        "zstandard",
    ]
