"""Esquemas Pydantic v2 de ADPRO / apu (request/response del contrato, docs/API_CONTRATO.md §3).

Decimales como ``Decimal`` (se serializan como string). Porcentajes como fracción (0.05 = 5 %).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.schemas import ORMModel
from app.modules.adpro.enums import TipoInsumo


# --- Requests ----------------------------------------------------------------------------
class ApuInsumoIn(BaseModel):
    insumo_id: int
    # Cantidad por unidad de ítem: Numeric(18,6) => hasta 6 decimales.
    cantidad: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    desperdicio_pct: Decimal = Field(default=Decimal("0"), ge=0, max_digits=9, decimal_places=6)
    orden: int | None = None
    observacion: str | None = Field(default=None, max_length=300)


class ApuInsumoUpdate(BaseModel):
    cantidad: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    desperdicio_pct: Decimal | None = Field(default=None, ge=0, max_digits=9, decimal_places=6)
    orden: int | None = None
    observacion: str | None = Field(default=None, max_length=300)


class ApuCreate(BaseModel):
    item_id: int
    descripcion: str | None = Field(default=None, max_length=300)
    observaciones: str | None = None
    insumos: list[ApuInsumoIn] = Field(default_factory=list)


class ApuUpdate(BaseModel):
    descripcion: str | None = Field(default=None, max_length=300)
    activo: bool | None = None
    observaciones: str | None = None


class ApuInsumosReemplazo(BaseModel):
    insumos: list[ApuInsumoIn]


class ApuCopia(BaseModel):
    item_id_destino: int
    descripcion: str | None = Field(default=None, max_length=300)


# --- Responses ---------------------------------------------------------------------------
class ApuInsumoOut(ORMModel):
    id: int
    insumo_id: int
    insumo_codigo: str
    insumo_descripcion: str
    unidad_codigo: str | None
    tipo: TipoInsumo
    cantidad: Decimal
    desperdicio_pct: Decimal
    orden: int
    observacion: str | None = None


class ApuOut(ORMModel):
    id: int
    item_id: int
    item_codigo: str
    item_descripcion: str
    unidad_codigo: str | None
    descripcion: str | None = None
    activo: bool
    observaciones: str | None = None
    num_insumos: int
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


class ApuDetalleOut(ApuOut):
    insumos: list[ApuInsumoOut]


class ComponenteOut(BaseModel):
    insumo_id: int
    insumo_codigo: str
    insumo_descripcion: str
    unidad_codigo: str | None
    tipo: TipoInsumo
    cantidad: Decimal
    desperdicio_pct: Decimal
    precio_unitario: Decimal
    valor_unitario: Decimal
    precio_faltante: bool
    lista_id: int | None = None


class ValorizacionOut(BaseModel):
    apu_id: int
    item_id: int
    ciudad_id: int
    fecha: date
    valor_unitario: Decimal
    insumos_sin_precio: list[int]
    subtotales_por_tipo: dict[str, Decimal]
    componentes: list[ComponenteOut]
