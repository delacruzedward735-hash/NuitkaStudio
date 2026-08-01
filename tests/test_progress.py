# SPDX-License-Identifier: MIT
from pathlib import Path
import unittest

from nuitka_gui.progress import detect_build_phase


class ProgressTests(unittest.TestCase):
    def test_detects_python_analysis_phase(self):
        phase = detect_build_phase("Nuitka: Starting Python compilation with:", 0.02)
        self.assertIsNotNone(phase)
        self.assertEqual(phase.label, "Analyzing Python modules")
        self.assertGreater(phase.start, 0.02)

    def test_detects_furthest_phase_in_batch(self):
        phase = detect_build_phase(
            "Nuitka: Generating source code for C backend compiler.\n"
            "Nuitka: Running C compilation via Scons.",
            0.20,
        )
        self.assertIsNotNone(phase)
        self.assertEqual(phase.label, "Compiling native code")

    def test_never_returns_older_phase(self):
        phase = detect_build_phase("Nuitka: Starting Python compilation with:", 0.70)
        self.assertIsNone(phase)

    def test_detects_phase_when_bar_reaches_phase_start(self):
        phase = detect_build_phase("Nuitka: Starting Python compilation with:", 0.08)
        self.assertIsNotNone(phase)
        self.assertEqual(phase.label, "Analyzing Python modules")

    def test_brand_assets_exist(self):
        assets = Path(__file__).resolve().parents[1] / "assets"
        for filename in (
            "nuitka-studio.ico",
            "nuitka-studio-icon-64.png",
            "nuitka-studio-icon-256.png",
        ):
            path = assets / filename
            self.assertTrue(path.is_file(), filename)
            self.assertGreater(path.stat().st_size, 1_000, filename)

    def test_navigation_icon_assets_exist(self):
        assets = Path(__file__).resolve().parents[1] / "assets"
        for name in ("build", "packages", "resources", "identity", "installer", "history", "settings", "help", "donate"):
            path = assets / f"nav-{name}.png"
            self.assertTrue(path.is_file(), path.name)
            self.assertGreater(path.stat().st_size, 200, path.name)


if __name__ == "__main__":
    unittest.main()
