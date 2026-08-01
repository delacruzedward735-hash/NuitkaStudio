# SPDX-License-Identifier: MIT
"""Small operating-system helpers used by Nuitka Studio."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import threading
import time
from typing import Any, Iterator, TextIO


WINDOWS_GUI_SUBSYSTEM = 2
WINDOWS_CONSOLE_SUBSYSTEM = 3


def mousewheel_scroll_units(platform: str, *, delta: int = 0, button_number: int | None = None) -> int:
    """Return a consistent vertical scroll amount for Tk wheel events.

    Linux/X11 commonly reports wheel movement as Button-4 and Button-5, while
    Windows, macOS, and some Wayland sessions use MouseWheel with a delta.
    Negative values scroll upward and positive values scroll downward.
    """
    if button_number == 4:
        return -3
    if button_number == 5:
        return 3
    if not delta:
        return 0
    if platform == "darwin":
        magnitude = max(1, min(8, abs(int(delta))))
    else:
        magnitude = max(1, min(8, abs(int(delta)) // 120 or 1)) * 3
    return -magnitude if delta > 0 else magnitude


def host_target_os() -> str:
    """Return the native build target supported by this Studio release."""
    platform = sys_platform()
    if os.name == "nt":
        return "windows"
    if platform.startswith("linux"):
        return "linux"
    raise RuntimeError(f"Nuitka Studio supports Windows and Linux hosts; detected {platform}.")


def detect_project_interpreter(entry_script: Path) -> Path | None:
    """Find a conventional Windows or Linux virtual environment near a project."""
    roots = (entry_script.parent, *entry_script.parent.parents[:3])
    relative_candidates = (
        Path(".venv") / "Scripts" / "python.exe",
        Path("venv") / "Scripts" / "python.exe",
        Path("env") / "Scripts" / "python.exe",
        Path(".venv") / "bin" / "python",
        Path("venv") / "bin" / "python",
        Path("env") / "bin" / "python",
    )
    for root in roots:
        for relative in relative_candidates:
            candidate = root / relative
            if candidate.is_file():
                return candidate
    return None


def is_private_environment_for_external_project(
    selected_python: Path,
    running_python: Path,
    running_prefix: Path,
    entry_script: Path,
) -> bool:
    """Detect using this tool's source venv to compile an unrelated project."""
    try:
        selected = selected_python.resolve()
        running = running_python.resolve()
        entry = entry_script.resolve()
        tool_root = running_prefix.resolve().parent
        return selected == running and ".venv" in {part.lower() for part in selected.parts} and not entry.is_relative_to(tool_root)
    except (OSError, ValueError):
        return False


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON without exposing a partially written settings file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def find_built_executable(
    output_directory: Path,
    output_filename: str,
    entry_script: Path,
    mode: str,
    *,
    target_os: str = "windows",
    built_after: float | None = None,
) -> Path | None:
    """Locate the executable produced by the current build, never a stale one."""
    filename = output_filename
    if target_os == "windows" and not filename.lower().endswith(".exe"):
        filename += ".exe"
    elif target_os == "linux" and filename.lower().endswith(".exe"):
        filename = filename[:-4]
    expected = [output_directory / filename]
    if mode == "standalone":
        expected = [
            output_directory / f"{entry_script.stem}.dist" / filename,
            output_directory / f"{Path(filename).stem}.dist" / filename,
            *expected,
        ]

    candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in (*expected, *output_directory.rglob(filename)):
        try:
            resolved = candidate.resolve()
            modified = candidate.stat().st_mtime
        except OSError:
            continue
        if resolved in seen or not candidate.is_file():
            continue
        if built_after is not None and modified < built_after - 5.0:
            continue
        seen.add(resolved)
        candidates.append(candidate)

    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def windows_pe_subsystem(executable: Path) -> int | None:
    """Read the PE subsystem: 2 is Windows GUI and 3 is Windows console."""
    try:
        with executable.open("rb") as stream:
            if stream.read(2) != b"MZ":
                return None
            stream.seek(0x3C)
            pe_offset_raw = stream.read(4)
            if len(pe_offset_raw) != 4:
                return None
            pe_offset = int.from_bytes(pe_offset_raw, "little")
            stream.seek(pe_offset)
            if stream.read(4) != b"PE\x00\x00":
                return None
            stream.seek(pe_offset + 24 + 68)
            subsystem = stream.read(2)
            return int.from_bytes(subsystem, "little") if len(subsystem) == 2 else None
    except OSError:
        return None


def is_linux_elf_executable(executable: Path) -> bool:
    """Confirm that a build artifact is an executable Linux ELF binary."""
    try:
        with executable.open("rb") as stream:
            return stream.read(4) == b"\x7fELF" and os.access(executable, os.X_OK)
    except OSError:
        return False


def create_linux_desktop_launcher(executable: Path, application_name: str, icon_path: Path | None = None) -> Path:
    """Create a portable desktop launcher beside a compiled Linux executable."""
    launcher_icon = ""
    if icon_path is not None and icon_path.is_file():
        copied_icon = executable.parent / f"{executable.name}-icon{icon_path.suffix.lower()}"
        if icon_path.resolve() != copied_icon.resolve():
            shutil.copy2(icon_path, copied_icon)
        launcher_icon = str(copied_icon)

    def escaped(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")

    launcher = executable.parent / f"{executable.name}.desktop"
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={application_name.replace(chr(10), ' ').replace(chr(13), ' ')}",
        f'Exec="{escaped(str(executable.resolve()))}"',
        "Terminal=false",
    ]
    if launcher_icon:
        lines.append(f'Icon={escaped(launcher_icon)}')
    lines.extend(("Categories=Utility;", ""))
    launcher.write_text("\n".join(lines), encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


def iter_batched_text_stream(
    stream: TextIO,
    *,
    max_chars: int = 16_384,
    max_lines: int = 32,
    max_delay: float = 0.05,
) -> Iterator[str]:
    """Yield bounded text batches without delaying quiet process output.

    A small reader thread is used because pipe reads are blocking on both
    Windows and Linux. The consumer flushes a partial batch after ``max_delay``
    even when the child process becomes quiet, preserving genuinely live logs.
    """
    items: queue.Queue[object] = queue.Queue()
    finished = object()

    def reader() -> None:
        try:
            for line in stream:
                items.put(line)
        finally:
            items.put(finished)

    threading.Thread(target=reader, name="nuitka-studio-output-reader", daemon=True).start()
    parts: list[str] = []
    characters = 0
    deadline = 0.0

    while True:
        timeout: float | None = None
        if parts:
            timeout = max(0.0, deadline - time.monotonic())
        try:
            item = items.get(timeout=timeout)
        except queue.Empty:
            yield "".join(parts)
            parts.clear()
            characters = 0
            deadline = 0.0
            continue

        if item is finished:
            if parts:
                yield "".join(parts)
            return

        line = str(item)
        if not parts:
            deadline = time.monotonic() + max(0.001, max_delay)
        parts.append(line)
        characters += len(line)
        if characters >= max_chars or len(parts) >= max_lines:
            yield "".join(parts)
            parts.clear()
            characters = 0
            deadline = 0.0


def terminate_process_tree(process: subprocess.Popen[str], timeout: float = 4.0) -> None:
    """Terminate a build and its compiler children, scoped to one process ID."""
    if process.poll() is not None:
        return

    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run(
                ["taskkill", "/PID", str(int(process.pid)), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(timeout, 1.0),
                check=False,
                creationflags=creationflags,
            )
        except (OSError, subprocess.SubprocessError):
            process.terminate()
        return

    try:
        process_group = os.getpgid(process.pid)
        os.killpg(process_group, signal.SIGTERM)
        deadline = time.monotonic() + timeout
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if process.poll() is None:
            os.killpg(process_group, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.terminate()
        except OSError:
            pass


def open_folder(path: Path) -> None:
    """Open a folder using the platform file manager."""
    resolved = path.resolve()
    if os.name == "nt":
        os.startfile(str(resolved))  # type: ignore[attr-defined]
    elif sys_platform() == "darwin":
        subprocess.Popen(["open", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["xdg-open", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reveal_file(path: Path) -> None:
    """Show the exact output artifact instead of an ambiguous parent folder."""
    resolved = path.resolve()
    if os.name == "nt":
        subprocess.Popen(
            ["explorer.exe", "/select,", str(resolved)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        open_folder(resolved.parent)


def sys_platform() -> str:
    import sys

    return sys.platform
