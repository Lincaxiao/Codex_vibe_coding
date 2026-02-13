#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
python -m unittest \
  focuslog.tests.test_cli \
  focuslog.tests.test_db \
  focuslog.tests.test_notifier \
  focuslog.tests.test_timer \
  focuslog.tests.test_stats \
  focuslog.tests.test_report \
  focuslog.tests.test_api
if command -v npm >/dev/null 2>&1 && [ -d focuslog/frontend/node_modules ]; then
  npm --prefix focuslog/frontend run test
else
  echo "[INFO] Skip frontend tests (npm or node_modules missing)."
fi
