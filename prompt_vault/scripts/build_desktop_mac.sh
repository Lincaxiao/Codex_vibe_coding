#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

echo "[INFO] Building frontend..."
npm --prefix prompt_vault/frontend install
npm --prefix prompt_vault/frontend run build

echo "[INFO] Building macOS desktop package..."
pyinstaller --noconfirm --windowed --name PromptVault \
  --paths . \
  --distpath prompt_vault/dist \
  --workpath prompt_vault/build \
  --specpath prompt_vault \
  prompt_vault/app_entry.py

echo "[OK] Desktop output: prompt_vault/dist/PromptVault.app"
