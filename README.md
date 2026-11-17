# ERP Prodesa

ERP propio de Prodesa, construido como **monolito modular**. Primer módulo: **ADPRO**
(presupuesto y control de obra): maestros de insumos y precios, EDT estilo ProdesaClass, APU,
presupuestos con versiones (BASE/FIC/FIV/CONTROL) inmutables al aprobarse, AIU, explosión de
insumos, comparativo entre versiones, compromisos, ejecución mensual, tablero e import/export Excel.

> Estado: **prototipo local** con datos 100 % sintéticos.

## Inicio rápido (Windows, Git Bash)

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m alembic upgrade head     # crea backend/erp_prodesa.db (SQLite)
./.venv/Scripts/python.exe -m app.seed                 # usuarios de prueba y catálogos básicos
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

- API y documentación interactiva: http://127.0.0.1:8000/docs
- Usuarios de prueba: `admin`, `presupuesto`, `obra`, `consulta`; contraseñas en `DEV_*` de tu `.env`. Si no están definidas, `app.seed` genera una aleatoria al crear los usuarios y la imprime una sola vez en consola. Solo desarrollo local.
- Tests: `./.venv/Scripts/python.exe -m pytest` (SQLite en memoria). Contra PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://usuario:clave@localhost:5432/bd_de_pruebas ./.venv/Scripts/python.exe -m pytest` (usa una BD dedicada: borra y recrea tablas).
- PostgreSQL opcional: `docker compose up -d db` (ver `.env.example`; exige `POSTGRES_PASSWORD`, y el perfil `app` además `JWT_SECRET`).

## Documentación
- [Arquitectura y estrategia a producción](docs/ARQUITECTURA.md)
- [Contrato de API](docs/API_CONTRATO.md)
- [Guía para agentes / desarrolladores](CLAUDE.md)
