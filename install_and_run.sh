#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "$0")"
export PYTHONUTF8=1
export PYTHONUNBUFFERED=1
export PIP_DISABLE_PIP_VERSION_CHECK=1

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10 or newer is required."
    echo "On Ubuntu/Debian/Kali/Parrot: sudo apt install python3 python3-venv python3-tk build-essential patchelf ccache dpkg"
    exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Python 3.10 or newer is required."
    exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
    echo "Creating the private Nuitka Studio environment..."
    python3 -m venv .venv
fi

.venv/bin/python bootstrap.py
exec .venv/bin/python run.py
