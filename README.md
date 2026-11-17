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
- Usuarios de prueba: `admin`, `presupuesto`, `obra`, `consulta`; contraseñas de prueba en `DEV_*` de tu `.env` (o el valor por defecto de `app/seed.py` si no hay `.env`). Solo desarrollo local.
- Tests: `./.venv/Scripts/python.exe -m pytest`
- PostgreSQL opcional: `docker compose up -d db` (ver `.env.example`).

## Documentación
- [Arquitectura y estrategia a producción](docs/ARQUITECTURA.md)
- [Contrato de API](docs/API_CONTRATO.md)
- [Guía para agentes / desarrolladores](CLAUDE.md)
