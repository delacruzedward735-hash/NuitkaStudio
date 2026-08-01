# SPDX-License-Identifier: MIT
"""Professional Windows Setup packaging through Inno Setup.

The functions in this module are GUI-independent so script generation and
validation can be tested on Linux, while the actual installer compiler is only
run on Windows by the application.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid


class WindowsInstallerError(RuntimeError):
    """Raised when a Windows Setup installer cannot be prepared or verified."""


@dataclass(frozen=True)
class WindowsInstallerConfig:
    executable: Path
    output_directory: Path
    application_name: str
    version: str
    publisher: str
    website: str = ""
    icon_path: Path | None = None
    license_path: Path | None = None
    mode: str = "standalone"
    install_scope: str = "all_users"
    desktop_shortcut: bool = True
    start_menu_shortcut: bool = True
    launch_after_install: bool = True
    compiler_path: Path | None = None


@dataclass
class PreparedWindowsInstaller:
    compiler_path: Path
    script_path: Path
    output_path: Path
    command: list[str]
    temporary_directory: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.temporary_directory, ignore_errors=True)


def _candidate_inno_paths() -> list[Path]:
    candidates: list[Path] = []
    for environment_name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(environment_name)
        if root:
            candidates.extend(
                (
                    Path(root) / "Inno Setup 6" / "ISCC.exe",
                    Path(root) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                    Path(root) / "Inno Setup 5" / "ISCC.exe",
                )
            )
    return candidates


def find_inno_setup_compiler(custom_path: str | Path | None = None) -> Path | None:
    """Locate ISCC.exe using a custom path, PATH, or common install folders."""
    if custom_path:
        custom = Path(custom_path).expanduser()
        if custom.is_file():
            return custom

    for command in ("ISCC.exe", "iscc.exe", "ISCC", "iscc"):
        found = shutil.which(command)
        if found and Path(found).is_file():
            return Path(found)

    for candidate in _candidate_inno_paths():
        if candidate.is_file():
            return candidate
    return None


def installer_output_filename(application_name: str, version: str) -> str:
    """Return a filesystem-safe setup filename."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", application_name.strip()).strip(".-_") or "Application"
    normalized_version = re.sub(r"[^0-9A-Za-z._-]+", "-", version.strip()).strip(".-_") or "1.0.0"
    return f"{stem}-Setup-{normalized_version}.exe"


def _inno_value(value: str | Path) -> str:
    """Escape a value placed inside a quoted Inno Setup parameter."""
    return str(value).replace('"', '""').replace("\r", " ").replace("\n", " ")


def _validate(config: WindowsInstallerConfig) -> tuple[Path, Path]:
    executable = config.executable.expanduser().resolve()
    output_directory = config.output_directory.expanduser().resolve()
    if not executable.is_file():
        raise WindowsInstallerError(f"Compiled Windows executable was not found: {executable}")
    if executable.suffix.lower() != ".exe":
        raise WindowsInstallerError("The installer entry point must be a Windows .exe file.")
    if config.mode not in {"standalone", "onefile"}:
        raise WindowsInstallerError("Installer source mode must be standalone or onefile.")
    if not config.application_name.strip():
        raise WindowsInstallerError("Enter an application name before creating the installer.")
    if not config.publisher.strip():
        raise WindowsInstallerError("Enter an installer publisher name.")
    if config.install_scope not in {"all_users", "current_user"}:
        raise WindowsInstallerError("Install scope must be all users or current user.")
    if config.icon_path is not None:
        icon = config.icon_path.expanduser().resolve()
        if not icon.is_file() or icon.suffix.lower() != ".ico":
            raise WindowsInstallerError("The Windows installer icon must be an existing .ico file.")
    if config.license_path is not None:
        license_file = config.license_path.expanduser().resolve()
        if not license_file.is_file():
            raise WindowsInstallerError("The selected installer license file does not exist.")
    output_directory.mkdir(parents=True, exist_ok=True)
    compiler = find_inno_setup_compiler(config.compiler_path)
    if compiler is None:
        raise WindowsInstallerError(
            "Inno Setup Compiler (ISCC.exe) was not found. Install Inno Setup 6 or select ISCC.exe on the Installer page."
        )
    return executable, compiler.resolve()


def generate_inno_script(config: WindowsInstallerConfig) -> tuple[str, Path]:
    """Generate a complete Inno Setup script and expected output path."""
    executable = config.executable.expanduser().resolve()
    output_directory = config.output_directory.expanduser().resolve()
    output_filename = installer_output_filename(config.application_name, config.version)
    output_base = Path(output_filename).stem
    app_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"nuitka-studio:{config.publisher.strip()}:{config.application_name.strip()}",
    )

    if config.install_scope == "all_users":
        default_directory = rf"{{autopf}}\{config.application_name.strip()}"
        privileges = "admin"
    else:
        default_directory = rf"{{localappdata}}\Programs\{config.application_name.strip()}"
        privileges = "lowest"

    lines = [
        "; Generated by Nuitka Studio. Review custom application requirements before distribution.",
        "[Setup]",
        f"AppId={{{{{str(app_id).upper()}}}}}",
        f'AppName={_inno_value(config.application_name.strip())}',
        f'AppVersion={_inno_value(config.version.strip() or "1.0.0")}',
        f'AppPublisher={_inno_value(config.publisher.strip())}',
        f'DefaultDirName={_inno_value(default_directory)}',
        f'DefaultGroupName={_inno_value(config.application_name.strip())}',
        f'OutputDir={_inno_value(output_directory)}',
        f'OutputBaseFilename={_inno_value(output_base)}',
        f'PrivilegesRequired={privileges}',
        "WizardStyle=modern",
        "Compression=lzma2/max",
        "SolidCompression=yes",
        "CloseApplications=yes",
        "RestartApplications=no",
        "RestartManagerSupport=yes",
        "DisableProgramGroupPage=yes",
        "UsePreviousAppDir=yes",
        "UsePreviousGroup=yes",
        "Uninstallable=yes",
        "UninstallLogging=yes",
        "UninstallLogMode=append",
        f'UninstallDisplayName={_inno_value(config.application_name.strip())}',
        f'UninstallDisplayIcon={{app}}\\{_inno_value(executable.name)}',
    ]
    if config.website.strip():
        website = _inno_value(config.website.strip())
        lines.extend((f"AppPublisherURL={website}", f"AppSupportURL={website}", f"AppUpdatesURL={website}"))
    if config.icon_path is not None:
        lines.append(f'SetupIconFile={_inno_value(config.icon_path.expanduser().resolve())}')
    if config.license_path is not None:
        lines.append(f'LicenseFile={_inno_value(config.license_path.expanduser().resolve())}')

    lines.extend(("", "[Languages]", 'Name: "english"; MessagesFile: "compiler:Default.isl"'))

    if config.desktop_shortcut:
        lines.extend(("", "[Tasks]", 'Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked'))

    lines.extend(("", "[Files]"))
    if config.mode == "standalone":
        source_root = executable.parent
        lines.append(
            f'Source: "{_inno_value(source_root)}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs'
        )
    else:
        lines.append(
            f'Source: "{_inno_value(executable)}"; DestDir: "{{app}}"; Flags: ignoreversion'
        )

    icon_entries: list[str] = []
    if config.start_menu_shortcut:
        icon_entries.append(
            f'Name: "{{group}}\\{_inno_value(config.application_name.strip())}"; Filename: "{{app}}\\{_inno_value(executable.name)}"; WorkingDir: "{{app}}"'
        )
    if config.desktop_shortcut:
        icon_entries.append(
            f'Name: "{{autodesktop}}\\{_inno_value(config.application_name.strip())}"; Filename: "{{app}}\\{_inno_value(executable.name)}"; WorkingDir: "{{app}}"; Tasks: desktopicon'
        )
    if icon_entries:
        lines.extend(("", "[Icons]", *icon_entries))

    if config.launch_after_install:
        lines.extend(
            (
                "",
                "[Run]",
                f'Filename: "{{app}}\\{_inno_value(executable.name)}"; Description: "Launch {_inno_value(config.application_name.strip())}"; WorkingDir: "{{app}}"; Flags: nowait postinstall skipifsilent',
            )
        )

    return "\n".join(lines) + "\n", output_directory / output_filename


def prepare_windows_installer(config: WindowsInstallerConfig) -> PreparedWindowsInstaller:
    """Validate configuration and create a temporary script ready for ISCC."""
    _executable, compiler = _validate(config)
    script, output_path = generate_inno_script(config)
    temporary_directory = Path(tempfile.mkdtemp(prefix="nuitka-studio-inno-"))
    script_path = temporary_directory / "installer.iss"
    try:
        script_path.write_text(script, encoding="utf-8-sig")
    except OSError:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    return PreparedWindowsInstaller(
        compiler_path=compiler,
        script_path=script_path,
        output_path=output_path,
        command=[str(compiler), str(script_path)],
        temporary_directory=temporary_directory,
    )
