"""Configuración central del backend (12-factor: todo por variables de entorno / .env).

Los valores por defecto están pensados SOLO para el prototipo local.

JWT_SECRET:
- ``ENVIRONMENT`` en {local, test}: si no se define (o se deja el valor de ejemplo público
  ``DEV_JWT_SECRET``) se usa un secreto ALEATORIO generado en esta máquina y guardado en
  ``backend/.jwt_secret.local`` (no versionado), así un token no se puede falsificar con un
  valor que está en el repositorio y las sesiones sobreviven a ``uvicorn --reload``.
- Cualquier otro entorno (staging, ci, production...): se EXIGE un JWT_SECRET propio de al
  menos 32 caracteres; si falta o es el de ejemplo, el arranque falla.
- ``production`` además prohíbe SQLite.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Valor de EJEMPLO público (está en el repo): nunca se usa para firmar tokens.
DEV_JWT_SECRET = "dev-solo-local-cambiar-en-produccion"  # noqa: S105 - valor de ejemplo
ENTORNOS_LOCALES = frozenset({"local", "test"})
JWT_SECRET_MIN_LEN = 32
_ARCHIVO_SECRETO_LOCAL = BACKEND_DIR / ".jwt_secret.local"


def _secreto_local() -> str:
    """Secreto aleatorio por máquina para desarrollo local (persistido, no versionado)."""
    try:
        guardado = _ARCHIVO_SECRETO_LOCAL.read_text(encoding="utf-8").strip()
        if len(guardado) >= JWT_SECRET_MIN_LEN:
            return guardado
    except OSError:
        pass
    nuevo = secrets.token_urlsafe(48)
    try:
        _ARCHIVO_SECRETO_LOCAL.write_text(nuevo, encoding="utf-8")
    except OSError:  # p. ej. sistema de archivos de solo lectura: vale solo para este proceso
        pass
    return nuevo


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "ERP Prodesa"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "local"  # local | test | staging | production

    # SQLite por defecto (cero instalación). Perfil prod-like (docker-compose):
    # postgresql+psycopg://erp:<password>@localhost:5432/erp_prodesa
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'erp_prodesa.db').as_posix()}"
    SQL_ECHO: bool = False

    # Autenticación
    AUTH_PROVIDER: str = "local"  # local | entra (Microsoft Entra ID, futuro)
    JWT_SECRET: str = ""  # vacío en local/test = aleatorio por máquina (ver docstring)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Microsoft Entra ID (futuro; no se usa en el prototipo)
    ENTRA_TENANT_ID: str | None = None
    ENTRA_CLIENT_ID: str | None = None

    # Lista separada por comas en .env: CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Usuarios de DESARROLLO creados por el seed (app/seed.py). Solo para local.
    DEV_ADMIN_USERNAME: str = "admin"
    DEV_ADMIN_PASSWORD: str | None = None
    DEV_USERS_PASSWORD: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _validar_secretos(self) -> Settings:
        secreto_debil = self.JWT_SECRET == DEV_JWT_SECRET or len(self.JWT_SECRET) < JWT_SECRET_MIN_LEN
        if self.ENVIRONMENT in ENTORNOS_LOCALES:
            if secreto_debil:
                self.JWT_SECRET = _secreto_local()
        elif secreto_debil:
            raise ValueError(
                f"ENVIRONMENT={self.ENVIRONMENT}: defina JWT_SECRET propio de al menos "
                f"{JWT_SECRET_MIN_LEN} caracteres (el valor de ejemplo no está permitido)"
            )
        if self.ENVIRONMENT == "production" and self.DATABASE_URL.startswith("sqlite"):
            raise ValueError("SQLite no está soportado en producción; use PostgreSQL")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
