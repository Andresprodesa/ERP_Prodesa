"""Configuración central del backend (12-factor: todo por variables de entorno / .env).

Los valores por defecto están pensados SOLO para el prototipo local. En producción
(`ENVIRONMENT=production`) se valida que no se usen secretos de desarrollo ni SQLite.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

DEV_JWT_SECRET = "dev-solo-local-cambiar-en-produccion"  # noqa: S105 - valor de desarrollo


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
    JWT_SECRET: str = DEV_JWT_SECRET
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
    def _validar_produccion(self) -> Settings:
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET == DEV_JWT_SECRET or len(self.JWT_SECRET) < 32:
                raise ValueError("JWT_SECRET de desarrollo o débil no permitido en producción")
            if self.DATABASE_URL.startswith("sqlite"):
                raise ValueError("SQLite no está soportado en producción; use PostgreSQL")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
