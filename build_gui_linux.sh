#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
    echo "Run ./install_and_run.sh first."
    exit 1
fi

exec .venv/bin/python -m nuitka \
    --mode=standalone \
    --assume-yes-for-downloads \
    --jobs=-2 \
    --enable-plugin=tk-inter \
    --include-package-data=customtkinter \
    --include-data-dir=assets=assets \
    --output-dir=release \
    --output-filename=NuitkaStudio \
    run.py
