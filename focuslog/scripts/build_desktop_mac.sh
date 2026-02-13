#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

echo "[INFO] Building frontend..."
npm --prefix focuslog/frontend install
npm --prefix focuslog/frontend run build

echo "[INFO] Building macOS desktop package..."
pyinstaller --noconfirm --windowed --name FocusLog \
  --paths . \
  --distpath focuslog/dist \
  --workpath focuslog/build \
  --specpath focuslog \
  focuslog/app_entry.py

echo "[OK] Desktop output: focuslog/dist/FocusLog.app"
