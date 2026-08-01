# SPDX-License-Identifier: MIT
"""Fast, repeatable dependency bootstrap for source launches of Nuitka Studio."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"
MARKER = Path(sys.prefix) / ".nuitka-studio-requirements.sha256"
REQUIRED_IMPORTS = (
    "customtkinter",
    "darkdetect",
    "packaging",
    "nuitka",
    "PIL",
    "zstandard",
    "ordered_set",
)


def dependency_fingerprint() -> str:
    """Include requirements and interpreter identity in the environment marker."""
    digest = hashlib.sha256()
    digest.update(REQUIREMENTS.read_bytes())
    digest.update(sys.version.encode("utf-8"))
    digest.update(sys.executable.encode("utf-8"))
    return digest.hexdigest()


def dependencies_ready(fingerprint: str) -> bool:
    """Verify the marker and package locations without importing heavy modules."""
    try:
        if MARKER.read_text(encoding="utf-8").strip() != fingerprint:
            return False
        for module_name in REQUIRED_IMPORTS:
            if importlib.util.find_spec(module_name) is None:
                return False
    except (OSError, ImportError, AttributeError, ValueError):
        return False
    return True


def run_checked(command: list[str]) -> None:
    print("Running:", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    try:
        fingerprint = dependency_fingerprint()
    except OSError as exc:
        print(f"Could not read requirements.txt: {exc}", file=sys.stderr)
        return 1

    if dependencies_ready(fingerprint):
        print("Dependencies are already ready; skipping pip installation.")
        return 0

    print("Installing or repairing Nuitka Studio dependencies...")
    try:
        run_checked([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        run_checked([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
        run_checked([sys.executable, "-m", "pip", "check"])
        MARKER.write_text(fingerprint + "\n", encoding="utf-8")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Dependency installation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
