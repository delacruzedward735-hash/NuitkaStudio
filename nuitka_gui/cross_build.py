# SPDX-License-Identifier: MIT
"""Generate native Windows and Linux Nuitka builds with GitHub Actions.

Nuitka binaries are platform-specific. This module does not pretend to perform
local cross-compilation; it creates a workflow that runs the Windows build on a
Windows runner and the Linux build on an Ubuntu runner.
"""

from __future__ import annotations

from dataclasses import replace
import base64
import json
from pathlib import Path
import re
from typing import Iterable

from .command_builder import BuildConfig, ConfigurationError, DataMapping, build_command


WORKFLOW_FILENAME = "nuitka-studio-cross-build.yml"
TARGET_WINDOWS = "windows"
TARGET_LINUX = "linux"
VALID_TARGETS = {TARGET_WINDOWS, TARGET_LINUX}
PYTHON_VERSION_RE = re.compile(r"^3\.(?:8|9|10|11|12|13|14)$")
ENTRY_SCRIPT_CANDIDATES = (
    "main.py",
    "app.py",
    "run.py",
    "main_onefile.py",
    "__main__.py",
    "src/main.py",
    "src/app.py",
)
IGNORED_DISCOVERY_DIRECTORIES = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "release",
    "tests",
    "test",
    "__pycache__",
    "node_modules",
    "site-packages",
}


class CrossBuildError(ValueError):
    """Raised when a cloud cross-build workflow cannot be generated safely."""


def path_is_inside_project(path_text: str, project_root: str) -> bool:
    """Return whether a path belongs to the selected project root.

    The check is intentionally tolerant of paths that do not exist yet so the
    GUI can validate edited fields without crashing while the user types.
    """
    value = path_text.strip()
    root_value = project_root.strip()
    if not value or not root_value:
        return False
    try:
        path = Path(value).expanduser()
        root = Path(root_value).expanduser().resolve()
        if not path.is_absolute():
            path = root / path
        path.resolve(strict=False).relative_to(root)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def detect_project_entry_script(project_root: str | Path) -> Path | None:
    """Find a conventional Python entry script inside a project folder.

    Direct conventional names are preferred. As a safe fallback, a single
    root-level Python file is accepted. A shallow recursive search is used only
    for conventional filenames and skips virtual environments and build output.
    """
    root = Path(project_root).expanduser()
    try:
        root = root.resolve()
    except OSError:
        return None
    if not root.is_dir():
        return None

    for relative_name in ENTRY_SCRIPT_CANDIDATES:
        candidate = root / relative_name
        if candidate.is_file():
            return candidate

    root_scripts = sorted(
        path for path in root.glob("*.py")
        if path.is_file() and path.name not in {"setup.py", "conftest.py"}
    )
    if len(root_scripts) == 1:
        return root_scripts[0]

    preferred_names = {Path(name).name for name in ENTRY_SCRIPT_CANDIDATES}
    discovered: list[Path] = []
    for path in root.rglob("*.py"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if len(relative.parts) > 3:
            continue
        if any(part in IGNORED_DISCOVERY_DIRECTORIES for part in relative.parts[:-1]):
            continue
        if path.name in preferred_names:
            discovered.append(path)
    if not discovered:
        return None
    discovered.sort(key=lambda item: (len(item.relative_to(root).parts), item.as_posix().casefold()))
    return discovered[0]


def _relative_file(path_text: str, project_root: Path, label: str, *, required: bool = False) -> str:
    value = path_text.strip()
    if not value:
        if required:
            raise CrossBuildError(f"{label} is required.")
        return ""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        resolved = path.resolve(strict=required)
        relative = resolved.relative_to(project_root)
    except FileNotFoundError as exc:
        raise CrossBuildError(f"{label} does not exist: {path}") from exc
    except ValueError as exc:
        raise CrossBuildError(
            f"{label} must be inside the selected project root so GitHub Actions can access it: {path}"
        ) from exc
    return relative.as_posix()


def _relative_mapping(mapping: DataMapping, project_root: Path) -> DataMapping:
    source = _relative_file(mapping.source, project_root, "Resource source", required=True)
    return DataMapping(source=source, destination=mapping.destination, kind=mapping.kind)


def _platform_config(
    config: BuildConfig,
    *,
    project_root: Path,
    target: str,
    windows_icon: str,
    linux_icon: str,
) -> BuildConfig:
    if target not in VALID_TARGETS:
        raise CrossBuildError(f"Unsupported cross-build target: {target}")

    entry_script = _relative_file(config.entry_script, project_root, "Entry script", required=True)
    mappings = [_relative_mapping(item, project_root) for item in config.data_mappings]
    icon = windows_icon if target == TARGET_WINDOWS else linux_icon
    relative_icon = _relative_file(icon, project_root, f"{target.title()} icon", required=True) if icon.strip() else ""

    output_stem = Path(config.output_filename.strip() or config.application_name.strip() or "Application").stem
    output_filename = f"{output_stem}.exe" if target == TARGET_WINDOWS else output_stem

    platform_config = replace(
        config,
        python_executable="python",
        entry_script=entry_script,
        output_directory="build",
        output_filename=output_filename,
        target_os=target,
        package_format="exe" if target == TARGET_WINDOWS else "elf",
        console_mode=config.console_mode if target == TARGET_WINDOWS and config.console_mode in {"disable", "force", "attach", "hide"} else ("disable" if target == TARGET_WINDOWS else "native"),
        compiler="auto",
        icon_path=relative_icon,
        data_mappings=mappings,
        installer_compiler="",
        installer_license="",
    )

    try:
        # Paths are repository-relative and do not exist in the local runner's
        # checkout yet, so validate structure without checking the filesystem.
        build_command(platform_config, require_paths=False)
    except ConfigurationError as exc:
        raise CrossBuildError(str(exc)) from exc
    return platform_config


def _encoded_build_arguments(config: BuildConfig) -> str:
    args = build_command(config, require_paths=False)[3:]
    payload = json.dumps(args, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(payload).decode("ascii")


def _artifact_slug(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-._")
    return cleaned or "application"


def _requirements_path(requirements_file: str, project_root: Path) -> str:
    value = requirements_file.strip()
    if not value:
        return ""
    # A requirements file can be absent while the workflow is being prepared;
    # GitHub will simply skip it if it remains absent.
    path = Path(value).expanduser()
    if path.is_absolute():
        try:
            return path.resolve().relative_to(project_root).as_posix()
        except ValueError as exc:
            raise CrossBuildError("Requirements file must be inside the selected project root.") from exc
    normalized = Path(value)
    if any(part == ".." for part in normalized.parts):
        raise CrossBuildError("Requirements file cannot leave the selected project root.")
    return normalized.as_posix()


def _job_yaml(
    config: BuildConfig,
    *,
    job_id: str,
    runner: str,
    python_version: str,
    requirements_file: str,
    artifact_name: str,
    enable_pip_cache: bool,
) -> str:
    encoded_args = _encoded_build_arguments(config)
    linux_tools = ""
    package_step = ""
    upload_path = ""

    if job_id == TARGET_LINUX:
        linux_tools = """
      - name: Install Linux build tools
        shell: bash
        run: |
          sudo apt-get update
          sudo apt-get install -y build-essential patchelf
"""
        package_step = f"""
      - name: Package Linux build
        shell: bash
        run: |
          mkdir -p release
          tar --exclude='*.build' --exclude='*.onefile-build' -czf "release/{artifact_name}.tar.gz" -C build .
"""
        upload_path = f"release/{artifact_name}.tar.gz"
    else:
        upload_path = """|
            build/*.exe
            build/*.dist/**"""

    requirements_json = json.dumps(requirements_file)
    pip_cache = ""
    if enable_pip_cache and requirements_file:
        pip_cache = (
            '          cache: "pip"\n'
            f'          cache-dependency-path: {json.dumps(requirements_file)}\n'
        )
    build_script = f"""import base64, json, shlex, subprocess, sys
args = json.loads(base64.b64decode(\"{encoded_args}\").decode(\"utf-8\"))
command = [sys.executable, \"-m\", \"nuitka\", *args]
print(\"Running:\", shlex.join(command))
subprocess.run(command, check=True)
"""
    build_script_indented = "\n".join(f"          {line}" for line in build_script.rstrip().splitlines())

    return f"""  {job_id}:
    name: {job_id.title()} native build
    runs-on: {runner}
    permissions:
      contents: read
    timeout-minutes: 120
    steps:
      - name: Check out project
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: {json.dumps(python_version)}
{pip_cache}{linux_tools}
      - name: Install project dependencies
        shell: bash
        env:
          REQUIREMENTS_FILE: {requirements_json}
        run: |
          python -m pip install --upgrade pip
          if [ -n "$REQUIREMENTS_FILE" ] && [ -f "$REQUIREMENTS_FILE" ]; then
            python -m pip install -r "$REQUIREMENTS_FILE"
          fi
          python -m pip install --upgrade nuitka ordered-set zstandard

      - name: Build with Nuitka
        shell: bash
        run: |
          python - <<'PY'
{build_script_indented}
          PY
{package_step}
      - name: Upload {job_id.title()} artifact
        uses: actions/upload-artifact@v4
        with:
          name: {artifact_name}
          path: {upload_path}
          if-no-files-found: error
          retention-days: 14
"""


def generate_cross_build_workflow(
    config: BuildConfig,
    *,
    project_root: str,
    python_version: str = "3.12",
    requirements_file: str = "requirements.txt",
    targets: Iterable[str] = (TARGET_WINDOWS, TARGET_LINUX),
    windows_icon: str = "",
    linux_icon: str = "",
    build_on_push: bool = False,
) -> str:
    """Return a GitHub Actions workflow for native Windows/Linux builds."""
    root_text = project_root.strip()
    if not root_text:
        raise CrossBuildError("Select the project root folder.")
    root = Path(root_text).expanduser().resolve()
    if not root.is_dir():
        raise CrossBuildError("The selected project root folder does not exist.")
    if not PYTHON_VERSION_RE.fullmatch(python_version.strip()):
        raise CrossBuildError("Python version must look like 3.12, 3.13, or 3.14.")

    selected_targets: list[str] = []
    for target in targets:
        normalized = str(target).strip().lower()
        if normalized not in VALID_TARGETS:
            raise CrossBuildError(f"Unsupported cross-build target: {target}")
        if normalized not in selected_targets:
            selected_targets.append(normalized)
    if not selected_targets:
        raise CrossBuildError("Select at least one target: Windows or Linux.")

    requirements = _requirements_path(requirements_file, root)
    enable_pip_cache = bool(requirements and (root / requirements).is_file())
    artifact_base = _artifact_slug(config.application_name or Path(config.entry_script).stem)

    trigger = """on:
  workflow_dispatch:
"""
    if build_on_push:
        trigger += """  push:
    branches:
      - main
      - master
"""

    jobs: list[str] = []
    if TARGET_WINDOWS in selected_targets:
        windows_config = _platform_config(
            config,
            project_root=root,
            target=TARGET_WINDOWS,
            windows_icon=windows_icon,
            linux_icon=linux_icon,
        )
        jobs.append(
            _job_yaml(
                windows_config,
                job_id=TARGET_WINDOWS,
                runner="windows-latest",
                python_version=python_version.strip(),
                requirements_file=requirements,
                artifact_name=f"{artifact_base}-windows",
                enable_pip_cache=enable_pip_cache,
            )
        )
    if TARGET_LINUX in selected_targets:
        linux_config = _platform_config(
            config,
            project_root=root,
            target=TARGET_LINUX,
            windows_icon=windows_icon,
            linux_icon=linux_icon,
        )
        jobs.append(
            _job_yaml(
                linux_config,
                job_id=TARGET_LINUX,
                runner="ubuntu-latest",
                python_version=python_version.strip(),
                requirements_file=requirements,
                artifact_name=f"{artifact_base}-linux",
                enable_pip_cache=enable_pip_cache,
            )
        )

    return f"""# Generated by Nuitka Studio. Builds run natively on each target OS.
name: Nuitka Studio Cross Build

{trigger}
env:
  PYTHONUTF8: "1"
  PYTHONUNBUFFERED: "1"
  PIP_DISABLE_PIP_VERSION_CHECK: "1"

concurrency:
  group: nuitka-cross-build-${{{{ github.ref }}}}
  cancel-in-progress: true

jobs:
{''.join(jobs)}"""


def write_cross_build_workflow(workflow_text: str, project_root: str) -> Path:
    """Write the generated workflow into .github/workflows atomically."""
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise CrossBuildError("The selected project root folder does not exist.")
    destination = root / ".github" / "workflows" / WORKFLOW_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(workflow_text, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return destination
