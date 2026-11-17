# CLAUDE.md — ERP Prodesa

## Qué es
ERP propio de **Prodesa** (constructora colombiana de vivienda VIS/VIP/No VIS). Hoy es un
**prototipo local** que se presentará a directivos y luego se escalará a producción.
Módulo 1: **ADPRO** = presupuesto y control de obra (maestros, APU, presupuesto con versiones,
comparativos, compromisos, ejecución, tablero, Excel). Diseño propio desde los procesos de
Prodesa; **no** copiar código, pantallas ni textos de productos de terceros (p. ej. Sinco).

Documentos clave (leer antes de programar):
- `docs/ARQUITECTURA.md` — decisiones, capas, convenciones, fórmulas, versionado, roadmap.
- `docs/API_CONTRATO.md` — TODOS los endpoints (fuente de verdad backend ↔ frontend).

## Stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x (`Mapped`/`mapped_column`), Pydantic v2,
  Alembic, pytest + TestClient, openpyxl. JWT local (PyJWT + bcrypt).
- BD: SQLite (por defecto, `backend/erp_prodesa.db`) / PostgreSQL 16 (`docker-compose.yml`, perfil prod-like).
- Frontend: React 18 + Vite + TypeScript, react-router, TanStack Query, estilo Manual de Marca
  Prodesa (skill `css-pro`).
- Arquitectura: monolito modular (`app/core` + `app/modules/<modulo>/<submodulo>`).

## Comandos (Windows + Git Bash, desde la raíz del repo)

```bash
# Backend: entorno
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
cp ../.env.example ../.env          # opcional; sin .env usa SQLite y valores de desarrollo

# BD + datos de prueba
./.venv/Scripts/python.exe -m alembic upgrade head
./.venv/Scripts/python.exe -m app.seed

# Tests y lint (obligatorio antes de entregar)
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m pytest tests/adpro/apu -q        # solo un submódulo
./.venv/Scripts/python.exe -m ruff check app tests && ./.venv/Scripts/python.exe -m ruff format app tests

# Servidor (http://127.0.0.1:8000/docs)
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload

# Nueva migración tras cambiar modelos (solo el arquitecto)
./.venv/Scripts/python.exe -m alembic revision --autogenerate -m "descripcion"

# PostgreSQL prod-like (requiere Docker Desktop corriendo)
docker compose up -d db   # y DATABASE_URL=postgresql+psycopg://erp:<pwd>@localhost:5432/erp_prodesa

# Frontend
cd frontend && npm install && npm run dev      # http://localhost:5173 (proxy /api -> :8000)
```

## Estructura y ZONAS DE PROPIEDAD (agentes)

| Zona | Dueño | Archivos |
|---|---|---|
| Fundación | arquitecto | `backend/app/core/**`, `app/main.py`, `app/db_models.py`, `app/seed.py`, `app/modules/adpro/{models,enums,calculos,valorizacion,router,__init__}.py`, `backend/alembic/**`, `tests/conftest.py`, `tests/core/**`, `tests/adpro/test_fundacion.py`, `docs/**`, `CLAUDE.md`, `README.md`, configs raíz |
| Maestros | agente maestros | `app/modules/adpro/maestros/**`, `tests/adpro/maestros/**` |
| APU | agente apu | `app/modules/adpro/apu/**`, `tests/adpro/apu/**` |
| Presupuesto | agente presupuesto | `app/modules/adpro/presupuesto/**`, `tests/adpro/presupuesto/**` |
| Control | agente control | `app/modules/adpro/control/**`, `tests/adpro/control/**` |
| Frontend | agente frontend | `frontend/**` |
| Datos demo | el que asigne el orquestador | `app/modules/adpro/seed_demo.py` (función `run(db) -> int`, la invoca `app.seed`) |

## Reglas para agentes
1. **Solo edita tu zona.** ¿Necesitas cambiar un modelo, `calculos.py`, `conftest.py` o el contrato? NO lo hagas: repórtalo (`model_change_requests` / `issues`).
2. **Datos sintéticos siempre**: nada de clientes, cédulas, NIT, cuentas bancarias ni credenciales reales. Terceros con nombres ficticios ("Proveedor Demo S.A.S.").
3. **Secretos solo por `.env`** (versionado solo `.env.example` con valores de prueba).
4. **Nunca `git push`.** Commits solo si la tarea lo pide (trailer `Co-Authored-By` indicado).
5. **Decimal** para dinero/cantidades/porcentajes (nunca float). Porcentajes como fracción. Fórmulas y redondeo SOLO vía `app.modules.adpro.calculos`; precios vigentes y APU vía `app.modules.adpro.valorizacion`.
6. **Tests obligatorios** para cada endpoint y regla de negocio (`pytest` verde antes de terminar). Usa fixtures de `tests/conftest.py` (`db`, `client`, `auth_client`, `client_as(rol)`, `make_user`, `seed_basico`); fixtures propias en `tests/adpro/<submodulo>/conftest.py`.
7. **Routers delgados** (validación + roles + llamada a service). `service.py` sin FastAPI, lanza `app.core.errors.*`, hace `db.commit()` y registra auditoría (`registrar_auditoria`) en cambios de estado/importaciones.
8. Respeta **exactamente** rutas, nombres de campos y roles de `docs/API_CONTRATO.md`. En cada `router.py` el prefijo ya está fijado (`/maestros`, `/apu`, `/presupuestos`, `/control`) y registrado en `/api/adpro`; declara rutas estáticas (`/edt/arbol`, `/apus/por-item/...`) **antes** de las parametrizadas (`/edt/{id}`).
9. Versiones APROBADAS/CERRADAS son inmutables (422 `BUSINESS_RULE`).
10. No dejes servidores corriendo en segundo plano. Código agnóstico de motor (SQLite y PostgreSQL).

## Estado
- v0.1: fundación lista (core, auth JWT, modelos ADPRO completos, migración `0001`, seed, tests de humo).
- Pendiente: implementación de submódulos maestros/apu/presupuesto/control y frontend según contrato.
