#!/usr/bin/env bash
# =====================================================================================
# ERP Prodesa - verificación local equivalente al CI (correr antes de abrir un PR).
#   ./scripts/check.sh            # lint + formato + tests backend + build frontend
#   ./scripts/check.sh --fix      # además aplica ruff --fix y ruff format antes de verificar
# =====================================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
if [[ -x .venv/Scripts/python.exe ]]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi

if [[ "${1:-}" == "--fix" ]]; then
  "$PY" -m ruff check --fix app tests
  "$PY" -m ruff format app tests
fi

echo "== ruff check";  "$PY" -m ruff check app tests
echo "== ruff format"; "$PY" -m ruff format --check app tests
echo "== pytest";      "$PY" -m pytest -q

if [[ -f "$ROOT/frontend/package.json" ]]; then
  cd "$ROOT/frontend"
  if [[ ! -d node_modules ]]; then
    if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
  fi
  echo "== frontend build"; npm run build
fi
echo "OK: verificación completa"
