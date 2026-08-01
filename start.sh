#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
    echo "Nuitka Studio is not installed yet. Run ./install_and_run.sh first."
    exit 1
fi

export PYTHONUTF8=1
export PYTHONUNBUFFERED=1
exec .venv/bin/python run.py
