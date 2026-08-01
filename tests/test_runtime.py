# SPDX-License-Identifier: MIT
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from nuitka_gui.runtime import (
    atomic_write_json,
    create_linux_desktop_launcher,
    detect_project_interpreter,
    find_built_executable,
    is_linux_elf_executable,
    is_private_environment_for_external_project,
    iter_batched_text_stream,
    mousewheel_scroll_units,
    terminate_process_tree,
    windows_pe_subsystem,
    WINDOWS_GUI_SUBSYSTEM,
)


class RuntimeTests(unittest.TestCase):
    def test_atomic_write_json_creates_valid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            atomic_write_json(path, {"name": "Nuitka Studio", "version": 3})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"name": "Nuitka Studio", "version": 3},
            )
            self.assertFalse((Path(directory) / "settings.json.tmp").exists())

    def test_atomic_write_json_replaces_previous_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"old": true}', encoding="utf-8")
            atomic_write_json(path, {"new": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": True})

    def test_terminate_process_tree_stops_scoped_process(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            text=True,
            start_new_session=sys.platform != "win32",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0),
        )
        try:
            terminate_process_tree(process, timeout=0.5)
            process.wait(timeout=3)
            self.assertIsNotNone(process.returncode)
        finally:
            if process.poll() is None:
                process.kill()


    def test_batched_stream_flushes_quiet_output_without_waiting_for_eof(self):
        class SlowStream:
            def __iter__(self):
                yield "first\n"
                time.sleep(0.08)
                yield "second\n"

        started = time.monotonic()
        batches = list(iter_batched_text_stream(SlowStream(), max_delay=0.01))
        elapsed = time.monotonic() - started
        self.assertEqual("".join(batches), "first\nsecond\n")
        self.assertGreaterEqual(len(batches), 2)
        self.assertLess(elapsed, 1.0)

    def test_normalizes_linux_mousewheel_buttons(self):
        self.assertEqual(mousewheel_scroll_units("linux", button_number=4), -3)
        self.assertEqual(mousewheel_scroll_units("linux", button_number=5), 3)

    def test_normalizes_windows_and_wayland_wheel_delta(self):
        self.assertEqual(mousewheel_scroll_units("win32", delta=120), -3)
        self.assertEqual(mousewheel_scroll_units("linux", delta=-120), 3)
        self.assertEqual(mousewheel_scroll_units("linux", delta=0), 0)

    def test_normalizes_macos_high_resolution_wheel(self):
        self.assertEqual(mousewheel_scroll_units("darwin", delta=1), -1)
        self.assertEqual(mousewheel_scroll_units("darwin", delta=-2), 2)

    def test_batched_stream_combines_noisy_output(self):
        class FastStream:
            def __iter__(self):
                yield from [f"line {index}\n" for index in range(10)]

        batches = list(iter_batched_text_stream(FastStream(), max_lines=4, max_delay=0.5))
        self.assertEqual("".join(batches), "".join(f"line {index}\n" for index in range(10)))
        self.assertLess(len(batches), 10)

    def test_detects_project_virtual_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            interpreter = root / ".venv" / "Scripts" / "python.exe"
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()
            entry = root / "src" / "main.py"
            entry.parent.mkdir()
            entry.touch()
            self.assertEqual(detect_project_interpreter(entry), interpreter)

    def test_detects_private_tool_environment_for_external_project(self):
        selected = Path("C:/Tools/NuitkaStudio/.venv/Scripts/python.exe")
        entry = Path("D:/Projects/NexaConvert/main.py")
        self.assertTrue(
            is_private_environment_for_external_project(
                selected,
                selected,
                Path("C:/Tools/NuitkaStudio/.venv"),
                entry,
            )
        )

    def test_finds_current_standalone_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "NexaConvert.exe"
            old.touch()
            os.utime(old, (10, 10))
            current = root / "main.dist" / "NexaConvert.exe"
            current.parent.mkdir()
            current.touch()
            os.utime(current, (100, 100))
            self.assertEqual(
                find_built_executable(
                    root,
                    "NexaConvert.exe",
                    Path("main.py"),
                    "standalone",
                    built_after=90,
                ),
                current,
            )

    def test_does_not_return_stale_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = root / "Demo.exe"
            stale.touch()
            os.utime(stale, (10, 10))
            self.assertIsNone(
                find_built_executable(root, "Demo.exe", Path("main.py"), "onefile", built_after=100)
            )

    def test_reads_windows_gui_pe_subsystem(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Demo.exe"
            payload = bytearray(512)
            payload[0:2] = b"MZ"
            payload[0x3C:0x40] = (0x80).to_bytes(4, "little")
            payload[0x80:0x84] = b"PE\x00\x00"
            subsystem_offset = 0x80 + 24 + 68
            payload[subsystem_offset:subsystem_offset + 2] = WINDOWS_GUI_SUBSYSTEM.to_bytes(2, "little")
            executable.write_bytes(payload)
            self.assertEqual(windows_pe_subsystem(executable), WINDOWS_GUI_SUBSYSTEM)

    def test_finds_and_verifies_linux_elf_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "main.dist" / "NexaConvert"
            executable.parent.mkdir()
            executable.write_bytes(b"\x7fELF" + b"\x00" * 32)
            executable.chmod(0o755)
            found = find_built_executable(
                root,
                "NexaConvert",
                Path("main.py"),
                "standalone",
                target_os="linux",
            )
            self.assertEqual(found, executable)
            self.assertTrue(is_linux_elf_executable(executable))

    def test_creates_linux_desktop_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "NexaConvert"
            executable.write_bytes(b"\x7fELF")
            executable.chmod(0o755)
            icon = root / "source.png"
            icon.write_bytes(b"PNG")
            launcher = create_linux_desktop_launcher(executable, "NexaConvert", icon)
            text = launcher.read_text(encoding="utf-8")
            self.assertIn("Terminal=false", text)
            self.assertIn("Name=NexaConvert", text)
            self.assertTrue(os.access(launcher, os.X_OK))


if __name__ == "__main__":
    unittest.main()
