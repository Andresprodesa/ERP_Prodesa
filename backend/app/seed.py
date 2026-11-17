"""Seed de DESARROLLO: usuarios de prueba y catálogos básicos (datos sintéticos).

Uso (desde backend/, después de ``alembic upgrade head``):

    .venv/Scripts/python.exe -m app.seed

Las contraseñas salen de ``DEV_ADMIN_PASSWORD`` / ``DEV_USERS_PASSWORD`` (.env). Si no están
definidas se usa un valor de prueba local. NUNCA ejecutar en producción (se bloquea).
Idempotente: no duplica registros existentes.

Los datos de demostración del dominio (insumos, APU, presupuestos de ejemplo) se agregan en
``app/modules/adpro/seed_demo.py`` (si existe) y se invocan desde aquí.
"""

from __future__ import annotations

import importlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401
from app.core.config import settings
from app.core.db import SESSION_USER_KEY, SessionLocal
from app.core.models import Rol, Usuario
from app.core.security import hash_password
from app.modules.adpro.models import Ciudad, Unidad

# Valor de PRUEBA solo para entornos locales sin .env (no es una credencial real).
_PASSWORD_PRUEBA_LOCAL = "Prodesa-Dev-2026"  # noqa: S105

USUARIOS_DEMO = [
    # username, nombre (ficticio), rol
    ("presupuesto", "Usuario Presupuesto (demo)", Rol.PRESUPUESTO),
    ("obra", "Usuario Obra (demo)", Rol.OBRA),
    ("consulta", "Usuario Consulta (demo)", Rol.CONSULTA),
]

UNIDADES = [
    ("UN", "Unidad"),
    ("ML", "Metro lineal"),
    ("M2", "Metro cuadrado"),
    ("M3", "Metro cúbico"),
    ("KG", "Kilogramo"),
    ("TON", "Tonelada"),
    ("GL", "Global"),
    ("LT", "Litro"),
    ("GAL", "Galón"),
    ("DIA", "Día"),
    ("HR", "Hora"),
    ("MES", "Mes"),
    ("VJE", "Viaje"),
    ("BTO", "Bulto"),
]

CIUDADES = [
    ("BOG", "Bogotá D.C.", "Cundinamarca", "Centro"),
    ("SOA", "Soacha", "Cundinamarca", "Centro"),
    ("MDE", "Medellín", "Antioquia", "Antioquia"),
    ("CLO", "Cali", "Valle del Cauca", "Occidente"),
    ("BAQ", "Barranquilla", "Atlántico", "Caribe"),
]


def _upsert_usuario(db: Session, username: str, nombre: str, rol: Rol, password: str) -> bool:
    if db.scalar(select(Usuario).where(Usuario.username == username)):
        return False
    db.add(Usuario(username=username, nombre=nombre, rol=rol, hashed_password=hash_password(password)))
    return True


def seed_usuarios(db: Session) -> int:
    admin_pwd = settings.DEV_ADMIN_PASSWORD or _PASSWORD_PRUEBA_LOCAL
    users_pwd = settings.DEV_USERS_PASSWORD or admin_pwd
    n = int(_upsert_usuario(db, settings.DEV_ADMIN_USERNAME, "Administrador (demo)", Rol.ADMIN, admin_pwd))
    for username, nombre, rol in USUARIOS_DEMO:
        n += int(_upsert_usuario(db, username, nombre, rol, users_pwd))
    return n


def seed_catalogos(db: Session) -> int:
    n = 0
    existentes_u = set(db.scalars(select(Unidad.codigo)))
    for codigo, nombre in UNIDADES:
        if codigo not in existentes_u:
            db.add(Unidad(codigo=codigo, nombre=nombre))
            n += 1
    existentes_c = set(db.scalars(select(Ciudad.codigo)))
    for codigo, nombre, depto, regional in CIUDADES:
        if codigo not in existentes_c:
            db.add(Ciudad(codigo=codigo, nombre=nombre, departamento=depto, regional=regional))
            n += 1
    return n


def run(db: Session) -> dict[str, int]:
    if settings.ENVIRONMENT == "production":
        raise RuntimeError("El seed de desarrollo no puede ejecutarse en producción")
    db.info[SESSION_USER_KEY] = "seed"
    res = {"usuarios": seed_usuarios(db), "catalogos": seed_catalogos(db)}
    db.commit()
    try:
        demo = importlib.import_module("app.modules.adpro.seed_demo")
    except ModuleNotFoundError:
        demo = None
    if demo is not None and hasattr(demo, "run"):
        res["demo"] = int(demo.run(db) or 0)
        db.commit()
    return res


def main() -> None:
    with SessionLocal() as db:
        res = run(db)
    print(f"Seed completado: {res}")  # noqa: T201


if __name__ == "__main__":
    main()
