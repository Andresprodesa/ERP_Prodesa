#!/usr/bin/env bash
# =====================================================================================
# ERP Prodesa - levanta el entorno LOCAL de desarrollo (backend FastAPI + frontend Vite).
#
# Uso (Git Bash en Windows, o Linux/macOS), desde la raíz del repo:
#   ./scripts/dev.sh                 # prepara venv, migra, siembra datos demo y levanta todo
#   ./scripts/dev.sh --reset-db      # borra la BD SQLite local y la recrea con datos demo
#   ./scripts/dev.sh --no-frontend   # solo backend
#   ./scripts/dev.sh --skip-seed     # no ejecuta el seed
#
# Backend:  http://127.0.0.1:8000/docs     Frontend: http://localhost:5173
# Ctrl+C detiene ambos procesos (no quedan servidores en segundo plano).
# Datos 100 % sintéticos. Las contraseñas de prueba salen de .env (ver .env.example).
# =====================================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RESET_DB=0
WITH_FRONTEND=1
SEED=1

for arg in "$@"; do
  case "$arg" in
    --reset-db) RESET_DB=1 ;;
    --no-frontend) WITH_FRONTEND=0 ;;
    --skip-seed) SEED=0 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '\033[1;34m[dev]\033[0m %s\n' "$*"; }

# --- Python del venv (Windows: Scripts/, Linux/macOS: bin/) ---------------------------
if [[ -x "$BACKEND/.venv/Scripts/python.exe" ]]; then
  PY="$BACKEND/.venv/Scripts/python.exe"
elif [[ -x "$BACKEND/.venv/bin/python" ]]; then
  PY="$BACKEND/.venv/bin/python"
else
  log "Creando entorno virtual en backend/.venv"
  (cd "$BACKEND" && python -m venv .venv)
  if [[ -x "$BACKEND/.venv/Scripts/python.exe" ]]; then PY="$BACKEND/.venv/Scripts/python.exe"; else PY="$BACKEND/.venv/bin/python"; fi
fi

# Reinstala dependencias solo si cambiaron los requirements
STAMP="$BACKEND/.venv/.requirements.stamp"
REQ_HASH="$(cat "$BACKEND/requirements.txt" "$BACKEND/requirements-dev.txt" | cksum | cut -d' ' -f1)"
if [[ ! -f "$STAMP" || "$(cat "$STAMP")" != "$REQ_HASH" ]]; then
  log "Instalando dependencias del backend"
  "$PY" -m pip install --disable-pip-version-check -q -r "$BACKEND/requirements-dev.txt"
  echo "$REQ_HASH" > "$STAMP"
fi

if [[ ! -f "$ROOT/.env" ]]; then
  log "No hay .env: se usan valores de desarrollo (SQLite). Copia .env.example a .env para personalizar."
fi

cd "$BACKEND"
if [[ "$RESET_DB" == 1 ]]; then
  log "Borrando BD SQLite local (backend/erp_prodesa.db)"
  rm -f "$BACKEND/erp_prodesa.db"
fi

log "Aplicando migraciones (alembic upgrade head)"
"$PY" -m alembic upgrade head
if [[ "$SEED" == 1 ]]; then
  log "Cargando datos de prueba sintéticos (idempotente)"
  "$PY" -m app.seed
fi

PIDS=()
cleanup() {
  log "Deteniendo procesos..."
  for pid in "${PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

log "Backend en http://127.0.0.1:8000 (docs: /docs)"
"$PY" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
PIDS+=($!)

if [[ "$WITH_FRONTEND" == 1 && -f "$FRONTEND/package.json" ]]; then
  cd "$FRONTEND"
  if [[ ! -d node_modules ]]; then
    log "Instalando dependencias del frontend"
    if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
  fi
  log "Frontend en http://localhost:5173"
  npm run dev &
  PIDS+=($!)
elif [[ "$WITH_FRONTEND" == 1 ]]; then
  log "No existe frontend/package.json: solo se levanta el backend."
fi

wait -n "${PIDS[@]}"
