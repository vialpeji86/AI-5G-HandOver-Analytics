#!/bin/zsh
set -e

APP_DIR="${0:A:h}"
cd "$APP_DIR"

if [ ! -d ".venv" ]; then
  echo "[Setup] Creating virtual environment..."
  python3 -m venv .venv
fi

PYTHON="$APP_DIR/.venv/bin/python"

if ! "$PYTHON" -c "import pandas, numpy, openpyxl" >/dev/null 2>&1; then
  echo "[Setup] Installing required packages..."
  "$PYTHON" -m pip install -U pip
  "$PYTHON" -m pip install -e .
fi

echo "[Run] Starting AI-5G-HandOver-Analytics..."
exec "$PYTHON" main.py
