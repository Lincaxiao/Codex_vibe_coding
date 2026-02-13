#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m unittest discover -s tests -p 'test_*.py' -v
if command -v npm >/dev/null 2>&1 && [ -d frontend/node_modules ]; then
  npm --prefix frontend run test
else
  echo "[INFO] Skip frontend tests (npm or node_modules missing)."
fi
