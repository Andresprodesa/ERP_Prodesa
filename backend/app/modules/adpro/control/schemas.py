"""Esquemas Pydantic v2 de ADPRO / control (request/response del contrato, §5).

Decimales como ``Decimal`` (se serializan como string). Porcentajes como fracción.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import AuditFields, ORMModel
from app.modules.adpro.enums import (
    EstadoCompromiso,
    EstadoVersion,
    TipoCompromiso,
    TipoInsumo,
    TipoVersion,
)

NivelComparativo = Literal["item", "insumo", "capitulo"]
EstadoComparativo = Literal["IGUAL", "MODIFICADO", "NUEVO", "ELIMINADO"]
ModoImportacion = Literal["agregar", "reemplazar"]

PERIODO_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


# =====================================================================================
# 5.1 Comparativo
# =====================================================================================
class VersionRef(ORMModel):
    id: int
    presupuesto_id: int
    numero: int
    nombre: str
    tipo: TipoVersion
    estado: EstadoVersion


class ComparativoFila(BaseModel):
    clave_id: int
    codigo: str
    descripcion: str
    unidad_codigo: str | None = None
    tipo: TipoInsumo | None = None  # solo nivel insumo
    capitulo_codigo: str | None = None
    # En nivel ``capitulo`` cantidades y unitarios no aplican (null).
    cantidad_base: Decimal | None = None
    cantidad_comparada: Decimal | None = None
    unitario_base: Decimal | None = None
    unitario_comparado: Decimal | None = None
    total_base: Decimal
    total_comparado: Decimal
    diferencia_cantidad: Decimal | None = None
    diferencia_unitaria: Decimal | None = None
    impacto: Decimal
    variacion_pct: Decimal | None = None
    estado: EstadoComparativo


class ComparativoTotales(BaseModel):
    total_base: Decimal
    total_comparado: Decimal
    impacto: Decimal
    variacion_pct: Decimal | None = None


class ComparativoOut(BaseModel):
    version_base: VersionRef
    version_comparada: VersionRef
    nivel: NivelComparativo
    filas: list[ComparativoFila]
    totales: ComparativoTotales


# =====================================================================================
# 5.2 Compromisos
# =====================================================================================
class CompromisoLineaIn(BaseModel):
    item_id: int
    insumo_id: int | None = None
    descripcion: str | None = Field(None, max_length=300)
    cantidad: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    valor_unitario: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class CompromisoCreate(BaseModel):
    presupuesto_id: int
    tipo: TipoCompromiso
    numero: str = Field(min_length=1, max_length=30)
    fecha: date
    tercero: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    lineas: list[CompromisoLineaIn] = Field(min_length=1)

    @field_validator("numero", "tercero")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("No puede estar vacío")
        return v


class CompromisoUpdate(BaseModel):
    """Actualización parcial. Si trae ``lineas`` las REEMPLAZA todas."""

    tipo: TipoCompromiso | None = None
    numero: str | None = Field(None, min_length=1, max_length=30)
    fecha: date | None = None
    tercero: str | None = Field(None, min_length=1, max_length=200)
    descripcion: str | None = None
    lineas: list[CompromisoLineaIn] | None = Field(None, min_length=1)


class CompromisoAnular(BaseModel):
    motivo: str = Field(min_length=1, max_length=500)


class CompromisoLineaOut(ORMModel):
    id: int
    item_id: int
    item_codigo: str
    item_descripcion: str
    insumo_id: int | None = None
    insumo_codigo: str | None = None
    descripcion: str | None = None
    cantidad: Decimal
    valor_unitario: Decimal
    valor_total: Decimal


class CompromisoOut(AuditFields):
    id: int
    presupuesto_id: int
    tipo: TipoCompromiso
    numero: str
    fecha: date
    tercero: str
    descripcion: str | None = None
    estado: EstadoCompromiso
    valor_total: Decimal
    num_lineas: int


class CompromisoDetalleOut(CompromisoOut):
    lineas: list[CompromisoLineaOut]
    advertencias: list[str] = Field(default_factory=list)


# =====================================================================================
# 5.3 Ejecución
# =====================================================================================
class EjecucionRegistroIn(BaseModel):
    item_id: int
    valor_ejecutado: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    cantidad_ejecutada: Decimal | None = Field(None, ge=0, max_digits=18, decimal_places=4)
    avance_fisico_pct: Decimal = Field(ge=0, le=1, decimal_places=6)
    compromiso_id: int | None = None
    observacion: str | None = Field(None, max_length=500)


class EjecucionLote(BaseModel):
    presupuesto_id: int
    periodo: str = Field(pattern=PERIODO_PATTERN, description="Periodo mensual YYYY-MM")
    registros: list[EjecucionRegistroIn] = Field(min_length=1)


class EjecucionLoteResultado(BaseModel):
    creados: int
    actualizados: int
    advertencias: list[str] = Field(default_factory=list)


class EjecucionOut(AuditFields):
    id: int
    presupuesto_id: int
    item_id: int
    item_codigo: str
    item_descripcion: str
    periodo: str
    valor_ejecutado: Decimal
    cantidad_ejecutada: Decimal | None = None
    avance_fisico_pct: Decimal
    compromiso_id: int | None = None
    observacion: str | None = None


# =====================================================================================
# 5.4 Tablero
# =====================================================================================
class TableroFila(BaseModel):
    id: int | None = None
    codigo: str
    descripcion: str
    presupuestado: Decimal
    comprometido: Decimal
    ejecutado: Decimal
    por_comprometer: Decimal
    saldo: Decimal
    pct_comprometido: Decimal | None = None
    pct_ejecutado: Decimal | None = None
    avance_fisico_pct: Decimal | None = None


class SerieMensualPunto(BaseModel):
    periodo: str
    ejecutado: Decimal
    ejecutado_acumulado: Decimal


class TableroOut(BaseModel):
    presupuesto_id: int
    version: VersionRef
    periodo_hasta: str | None = None
    capitulos: list[TableroFila]
    totales: TableroFila
    serie_mensual: list[SerieMensualPunto]


# =====================================================================================
# 5.5 Excel
# =====================================================================================
class ImportErrorFila(BaseModel):
    fila: int
    columna: str | None = None
    mensaje: str


class ImportResultado(BaseModel):
    aplicado: bool
    lineas_creadas: int = 0
    lineas_actualizadas: int = 0
    lineas_eliminadas: int = 0
    errores: list[ImportErrorFila] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)
