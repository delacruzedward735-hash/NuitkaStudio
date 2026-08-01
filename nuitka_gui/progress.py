# SPDX-License-Identifier: MIT
"""Phase-based progress detection for Nuitka compiler output."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildPhase:
    start: float
    ceiling: float
    label: str


PHASE_PATTERNS: tuple[tuple[str, BuildPhase], ...] = (
    ("starting python compilation", BuildPhase(0.08, 0.28, "Analyzing Python modules")),
    ("completed python level compilation", BuildPhase(0.32, 0.39, "Python analysis complete")),
    ("generating source code", BuildPhase(0.42, 0.52, "Generating C source")),
    ("data composer", BuildPhase(0.53, 0.59, "Preparing constants and data")),
    ("running c compilation", BuildPhase(0.60, 0.84, "Compiling native code")),
    ("backend c compiler", BuildPhase(0.64, 0.84, "Compiling native code")),
    ("backend linking", BuildPhase(0.86, 0.92, "Linking executable")),
    ("compressing onefile", BuildPhase(0.93, 0.98, "Compressing onefile package")),
    ("onefile payload", BuildPhase(0.93, 0.98, "Packaging onefile executable")),
    ("successfully created", BuildPhase(0.99, 1.0, "Finalizing output")),
)


def detect_build_phase(output: str, current_progress: float) -> BuildPhase | None:
    """Return the furthest new build phase found in an output batch."""
    lowered = output.lower()
    matches = [phase for pattern, phase in PHASE_PATTERNS if pattern in lowered and phase.ceiling > current_progress]
    return max(matches, key=lambda phase: phase.start) if matches else None
