"""Esquemas Pydantic v2 compartidos por todos los módulos.

Convenciones de contrato JSON:
- Decimales (dinero, cantidades, porcentajes) viajan como STRING ("1234.5000") para no
  perder precisión. Los porcentajes son FRACCIÓN ("0.050000" = 5 %).
- Fechas ISO-8601 ("2026-11-17"); timestamps ISO con zona horaria.
- Listados paginados devuelven ``Page[T]``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

# Enteros de entrada que se guardan en columnas INTEGER (int32 en PostgreSQL): ids, orden, etc.
# Sin este límite, 99999999999 pasa la validación y PostgreSQL responde 'integer out of range'.
INT32_MAX = 2_147_483_647
Int32 = Annotated[int, Field(ge=-INT32_MAX - 1, le=INT32_MAX)]
Id = Annotated[int, Field(ge=1, le=INT32_MAX)]


class ORMModel(BaseModel):
    """Base para respuestas construidas desde modelos SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True)


class AuditFields(ORMModel):
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams(BaseModel):
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class Message(BaseModel):
    message: str
