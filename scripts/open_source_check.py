#!/usr/bin/env python3
"""Validate the repository before a public release."""

from __future__ import annotations

import argparse
import compileall
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "3.9.3"
REQUIRED_FILES = (
    "LICENSE",
    "README.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    "THIRD_PARTY_NOTICES.md",
    "NOTICE",
    ".github/workflows/tests.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
)
TEXT_EXTENSIONS = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".sh", ".bat", ".iss", ".cff"}
EXCLUDED_DIRS = {".git", ".venv", "build", "dist", "release", "installer-output", "__pycache__"}
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "generic private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
}
ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9_])/home/[A-Za-z0-9_.-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\r\n]+"),
)
ALLOWED_ABSOLUTE_PATH_FILES = {Path("tests/test_command_builder.py")}


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)
    print(f"ERROR: {message}")


def check_required_files(errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}", errors)


def check_versions(errors: list[str]) -> None:
    checks = {
        "nuitka_gui/app.py": f'APP_VERSION = "{EXPECTED_VERSION}"',
        "nuitka_gui/__init__.py": f'__version__ = "{EXPECTED_VERSION}"',
        "installer.iss": f'#define MyAppVersion "{EXPECTED_VERSION}"',
        "CITATION.cff": f'version: "{EXPECTED_VERSION}"',
    }
    for relative, marker in checks.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        if marker not in text:
            fail(f"version marker mismatch in {relative}: expected {marker}", errors)


def check_secrets_and_paths(errors: list[str]) -> None:
    for path in iter_text_files():
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                fail(f"possible {label} in {relative}", errors)
        if relative not in ALLOWED_ABSOLUTE_PATH_FILES:
            for pattern in ABSOLUTE_PATH_PATTERNS:
                if pattern.search(text):
                    fail(f"possible personal absolute path in {relative}", errors)


def check_donation_config(errors: list[str]) -> None:
    path = ROOT / "assets/donation_config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"invalid donation configuration: {exc}", errors)
        return
    number = "".join(ch for ch in str(data.get("gcash_number", "")) if ch.isdigit())
    if number and len(number) < 10:
        fail("GCash number appears incomplete", errors)


def check_compile(errors: list[str]) -> None:
    targets = [ROOT / "nuitka_gui", ROOT / "tests", ROOT / "scripts"]
    for target in targets:
        if not compileall.compile_dir(target, quiet=1, force=True):
            fail(f"Python compilation failed under {target.relative_to(ROOT)}", errors)
    for target in (ROOT / "run.py", ROOT / "bootstrap.py"):
        if not compileall.compile_file(target, quiet=1, force=True):
            fail(f"Python compilation failed for {target.name}", errors)


def run_tests(errors: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode:
        fail(f"automated tests failed with exit code {result.returncode}", errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true", help="skip the unittest suite")
    args = parser.parse_args()

    errors: list[str] = []
    check_required_files(errors)
    check_versions(errors)
    check_secrets_and_paths(errors)
    check_donation_config(errors)
    check_compile(errors)
    if not args.skip_tests:
        run_tests(errors)

    if errors:
        print(f"\nOpen-source readiness check failed with {len(errors)} issue(s).")
        return 1
    print("\nOpen-source readiness check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
