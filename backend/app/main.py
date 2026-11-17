"""Punto de entrada FastAPI del ERP Prodesa (monolito modular).

Ejecutar (desde backend/):  .venv/Scripts/python.exe -m uvicorn app.main:app --reload
Documentación interactiva:  http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401  (registra todos los modelos)
from app.core.auth_router import audit_router
from app.core.auth_router import router as auth_router
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import register_exception_handlers
from app.modules.adpro.router import router as adpro_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="ERP Prodesa - prototipo local. Módulo 1: ADPRO (presupuesto y control de obra).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    register_exception_handlers(app)

    @app.get("/api/health", tags=["Sistema"])
    def health(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
        db_ok = True
        try:
            db.execute(text("SELECT 1"))
        except Exception:  # pragma: no cover - depende del entorno
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "database": "ok" if db_ok else "error",
        }

    app.include_router(auth_router)
    app.include_router(audit_router)
    app.include_router(adpro_router)
    # Futuros módulos: app.include_router(compras_router), etc.
    return app


app = create_app()
