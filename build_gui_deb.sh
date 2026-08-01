#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
    echo "Run ./install_and_run.sh first."
    exit 1
fi
if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "dpkg-deb is required. Install the dpkg package first."
    exit 1
fi

.venv/bin/python -m nuitka \
    --mode=standalone \
    --assume-yes-for-downloads \
    --jobs=-2 \
    --enable-plugin=tk-inter \
    --include-package-data=customtkinter \
    --include-data-dir=assets=assets \
    --output-dir=release \
    --output-filename=NuitkaStudio \
    run.py

.venv/bin/python - <<'PY'
from pathlib import Path

from nuitka_gui.deb_package import DebianPackageConfig, build_debian_package
from nuitka_gui.runtime import find_built_executable, is_linux_elf_executable

root = Path.cwd()
release = root / "release"
executable = find_built_executable(
    release,
    "NuitkaStudio",
    root / "run.py",
    "standalone",
    target_os="linux",
)
if executable is None or not is_linux_elf_executable(executable):
    raise SystemExit("The compiled Nuitka Studio ELF executable could not be verified.")

package = build_debian_package(
    DebianPackageConfig(
        executable=executable,
        output_directory=release,
        package_id="nuitka-studio",
        application_name="Nuitka Studio",
        version="3.9.3",
        maintainer="John Edward Dela Cruz",
        description="Modern desktop frontend for the Nuitka Python compiler",
        icon_path=root / "assets" / "nuitka-studio-icon-256.png",
        mode="standalone",
    )
)
print(f"Created {package}")
PY
