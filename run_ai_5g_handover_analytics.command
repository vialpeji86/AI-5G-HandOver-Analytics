#!/bin/zsh
set -e

APP_DIR="${0:A:h}"
cd "$APP_DIR"

if [ ! -d ".venv" ]; then
  echo "[Setup] Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import pandas, numpy, openpyxl, tkinterdnd2" >/dev/null 2>&1; then
  echo "[Setup] Installing required packages..."
  pip install -U pip
  pip install -e .
fi

echo "[Run] Starting AI-5G-HandOver-Analytics..."
python main.py
