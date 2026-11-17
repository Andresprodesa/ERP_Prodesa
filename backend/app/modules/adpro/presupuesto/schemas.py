"""Esquemas Pydantic v2 de ADPRO / presupuesto (contrato: docs/API_CONTRATO.md §4).

Decimales como ``Decimal`` (se serializan como string). Porcentajes como fracción (0.05 = 5 %).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.schemas import Int32, ORMModel
from app.modules.adpro.enums import EstadoVersion, OrigenValor, TipoInsumo, TipoVersion


class _Auditoria(ORMModel):
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


# =====================================================================================
# Presupuestos
# =====================================================================================
class PresupuestoCreate(BaseModel):
    proyecto_id: int
    etapa_id: int | None = None
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None


class PresupuestoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None


class PresupuestoOut(_Auditoria):
    id: int
    proyecto_id: int
    proyecto_codigo: str
    proyecto_nombre: str
    etapa_id: int | None = None
    etapa_codigo: str | None = None
    codigo: str
    nombre: str
    descripcion: str | None = None
    num_versiones: int


# =====================================================================================
# Versiones
# =====================================================================================
def _pct(default: str | None = None) -> object:
    if default is None:
        return Field(default=None, ge=0, le=1, max_digits=9, decimal_places=6)
    return Field(default=Decimal(default), ge=0, le=1, max_digits=9, decimal_places=6)


class VersionCreate(BaseModel):
    tipo: TipoVersion
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    fecha_precios: date
    ciudad_precios_id: int | None = None
    administracion_pct: Decimal = _pct("0")  # type: ignore[assignment]
    imprevistos_pct: Decimal = _pct("0")  # type: ignore[assignment]
    utilidad_pct: Decimal = _pct("0")  # type: ignore[assignment]
    iva_utilidad_pct: Decimal = _pct("0.19")  # type: ignore[assignment]


class VersionUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None
    fecha_precios: date | None = None
    ciudad_precios_id: int | None = None
    administracion_pct: Decimal | None = _pct()  # type: ignore[assignment]
    imprevistos_pct: Decimal | None = _pct()  # type: ignore[assignment]
    utilidad_pct: Decimal | None = _pct()  # type: ignore[assignment]
    iva_utilidad_pct: Decimal | None = _pct()  # type: ignore[assignment]


class TransicionIn(BaseModel):
    observacion: str | None = Field(default=None, max_length=500)


class VersionCopy(BaseModel):
    tipo: TipoVersion
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    presupuesto_id_destino: int | None = None
    recalcular_precios: bool = False
    fecha_precios: date | None = None


class VersionOut(_Auditoria):
    id: int
    presupuesto_id: int
    numero: int
    tipo: TipoVersion
    estado: EstadoVersion
    nombre: str
    descripcion: str | None = None
    fecha_precios: date
    ciudad_precios_id: int
    ciudad_precios_codigo: str | None = None
    administracion_pct: Decimal
    imprevistos_pct: Decimal
    utilidad_pct: Decimal
    iva_utilidad_pct: Decimal
    version_origen_id: int | None = None
    aprobado_at: datetime | None = None
    aprobado_por: str | None = None
    cerrado_at: datetime | None = None
    cerrado_por: str | None = None
    total_costo_directo: Decimal
    total_presupuesto: Decimal
    num_lineas: int
    editable: bool


class PresupuestoDetalleOut(PresupuestoOut):
    versiones: list[VersionOut]


class RecalculoOut(BaseModel):
    version_id: int
    lineas_recalculadas: int
    insumos_sin_precio: list[int]
    # ítems de líneas origen APU que NO se revalorizaron (su APU no existe o está inactivo)
    items_sin_apu: list[int] = Field(default_factory=list)
    total_costo_directo: Decimal


# =====================================================================================
# Líneas
# =====================================================================================
class LineaCreate(BaseModel):
    item_id: int
    cantidad: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    valor_unitario: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    observacion: str | None = Field(default=None, max_length=500)


class LineaUpdate(BaseModel):
    cantidad: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    valor_unitario: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    observacion: str | None = Field(default=None, max_length=500)
    orden: Int32 | None = None


class LineasLote(BaseModel):
    lineas: list[LineaCreate] = Field(min_length=1)


class ErrorLinea(BaseModel):
    indice: int
    mensaje: str


class LoteResultado(BaseModel):
    creadas: int
    errores: list[ErrorLinea]


class LineaOut(_Auditoria):
    id: int
    version_id: int
    item_id: int
    item_codigo: str
    item_descripcion: str
    unidad_codigo: str | None = None
    capitulo_id: int | None = None
    capitulo_codigo: str | None = None
    capitulo_descripcion: str | None = None
    cantidad: Decimal
    valor_unitario: Decimal
    valor_total: Decimal
    origen_unitario: OrigenValor
    orden: int
    observacion: str | None = None
    num_insumos: int
    insumos_sin_precio: list[int]


class LineaInsumoOut(BaseModel):
    insumo_id: int
    insumo_codigo: str
    insumo_descripcion: str
    unidad_codigo: str | None = None
    tipo: TipoInsumo
    cantidad_unitaria: Decimal
    desperdicio_pct: Decimal
    precio_unitario: Decimal
    valor_unitario: Decimal
    precio_faltante: bool
    cantidad_total: Decimal
    valor_total: Decimal


# =====================================================================================
# Resumen (AIU) y explosión
# =====================================================================================
class CapituloTotal(BaseModel):
    capitulo_id: int | None
    codigo: str
    descripcion: str
    valor: Decimal
    participacion_pct: Decimal
    num_lineas: int


class ResumenOut(BaseModel):
    version_id: int
    capitulos: list[CapituloTotal]
    costo_directo: Decimal
    administracion_pct: Decimal
    imprevistos_pct: Decimal
    utilidad_pct: Decimal
    iva_utilidad_pct: Decimal
    administracion: Decimal
    imprevistos: Decimal
    utilidad: Decimal
    iva_utilidad: Decimal
    total_aiu: Decimal
    total: Decimal
    num_lineas: int
    lineas_sin_precio: int


class ExplosionFila(BaseModel):
    insumo_id: int
    insumo_codigo: str
    insumo_descripcion: str
    unidad_codigo: str | None = None
    tipo: TipoInsumo
    cantidad_total: Decimal
    precio_unitario: Decimal
    valor_total: Decimal
    participacion_pct: Decimal


class ExplosionTipo(BaseModel):
    tipo: TipoInsumo
    valor_total: Decimal
    participacion_pct: Decimal


class ExplosionOut(BaseModel):
    version_id: int
    filas: list[ExplosionFila]
    por_tipo: list[ExplosionTipo]
    total_insumos: Decimal
    valor_sin_desglose: Decimal
    total: Decimal
