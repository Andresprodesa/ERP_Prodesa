"""Esquemas Pydantic v2 de ADPRO / maestros (request/response del contrato).

Usar ``app.core.schemas.ORMModel`` como base de respuestas y ``Page[T]`` para listados.
Decimales como ``Decimal`` (se serializan como string). Porcentajes como fracción.

Las respuestas con campos derivados de relaciones (``unidad_codigo``, ``ciudad_codigo``...) se
construyen con los métodos de clase ``desde(...)`` para no depender de alias ni de carga perezosa.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.core.schemas import AuditFields, Int32
from app.modules.adpro.enums import EstadoProyecto, NivelEdt, TipoInsumo, TipoProyecto
from app.modules.adpro.models import (
    EdtNodo,
    Etapa,
    Insumo,
    ListaPrecios,
    PrecioInsumo,
    Proyecto,
)

# --- Tipos reutilizables -------------------------------------------------------------------
_CODIGO_RE = r"^[A-Za-z0-9][A-Za-z0-9._\-]*$"


def _codigo(max_len: int) -> type[str]:
    return Annotated[  # type: ignore[return-value]
        str,
        StringConstraints(
            strip_whitespace=True, to_upper=True, min_length=1, max_length=max_len, pattern=_CODIGO_RE
        ),
    ]


def _texto(max_len: int) -> type[str]:
    return Annotated[  # type: ignore[return-value]
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_len)
    ]


Codigo10 = _codigo(10)
Codigo30 = _codigo(30)
Texto100 = _texto(100)
Texto200 = _texto(200)
Texto300 = _texto(300)
TextoLibre = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Precio = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]
EnteroNoNegativo = Annotated[int, Field(ge=0)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# =========================================================================================
# Unidades y ciudades
# =========================================================================================
class UnidadCreate(_In):
    codigo: Codigo10
    nombre: Texto100
    activo: bool = True


class UnidadUpdate(_In):
    codigo: Codigo10 | None = None
    nombre: Texto100 | None = None
    activo: bool | None = None


class UnidadOut(AuditFields):
    id: int
    codigo: str
    nombre: str
    activo: bool


class CiudadCreate(_In):
    codigo: Codigo10
    nombre: Texto100
    departamento: Texto100 | None = None
    regional: Texto100 | None = None
    activo: bool = True


class CiudadUpdate(_In):
    codigo: Codigo10 | None = None
    nombre: Texto100 | None = None
    departamento: Texto100 | None = None
    regional: Texto100 | None = None
    activo: bool | None = None


class CiudadOut(AuditFields):
    id: int
    codigo: str
    nombre: str
    departamento: str | None = None
    regional: str | None = None
    activo: bool


# =========================================================================================
# Insumos
# =========================================================================================
class InsumoCreate(_In):
    codigo: Codigo30
    descripcion: Texto300
    unidad_id: int
    tipo: TipoInsumo
    activo: bool = True
    observaciones: TextoLibre | None = None


class InsumoUpdate(_In):
    codigo: Codigo30 | None = None
    descripcion: Texto300 | None = None
    unidad_id: int | None = None
    tipo: TipoInsumo | None = None
    activo: bool | None = None
    observaciones: TextoLibre | None = None


class InsumoOut(AuditFields):
    id: int
    codigo: str
    descripcion: str
    unidad_id: int
    unidad_codigo: str
    tipo: TipoInsumo
    activo: bool
    observaciones: str | None = None

    @classmethod
    def desde(cls, i: Insumo) -> InsumoOut:
        return cls(
            id=i.id,
            codigo=i.codigo,
            descripcion=i.descripcion,
            unidad_id=i.unidad_id,
            unidad_codigo=i.unidad.codigo,
            tipo=i.tipo,
            activo=i.activo,
            observaciones=i.observaciones,
            created_at=i.created_at,
            updated_at=i.updated_at,
            created_by=i.created_by,
            updated_by=i.updated_by,
        )


class PrecioHistoricoOut(BaseModel):
    lista_id: int
    lista_codigo: str
    lista_nombre: str
    ciudad_id: int
    ciudad_codigo: str
    fecha_desde: date
    precio: Decimal


# =========================================================================================
# Listas de precios
# =========================================================================================
class ListaPreciosCreate(_In):
    codigo: Codigo30
    nombre: Texto200
    ciudad_id: int
    fecha_desde: date
    observaciones: TextoLibre | None = None
    copiar_de_lista_id: int | None = None


class ListaPreciosUpdate(_In):
    nombre: Texto200 | None = None
    activo: bool | None = None
    observaciones: TextoLibre | None = None


class ListaPreciosOut(AuditFields):
    id: int
    codigo: str
    nombre: str
    ciudad_id: int
    ciudad_codigo: str
    fecha_desde: date
    activo: bool
    observaciones: str | None = None
    num_precios: int

    @classmethod
    def desde(cls, lista: ListaPrecios, num_precios: int) -> ListaPreciosOut:
        return cls(
            id=lista.id,
            codigo=lista.codigo,
            nombre=lista.nombre,
            ciudad_id=lista.ciudad_id,
            ciudad_codigo=lista.ciudad.codigo,
            fecha_desde=lista.fecha_desde,
            activo=lista.activo,
            observaciones=lista.observaciones,
            num_precios=num_precios,
            created_at=lista.created_at,
            updated_at=lista.updated_at,
            created_by=lista.created_by,
            updated_by=lista.updated_by,
        )


class PrecioIn(_In):
    insumo_id: int
    precio: Precio
    fuente: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class PreciosLote(_In):
    precios: list[PrecioIn] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def _sin_repetidos(self) -> PreciosLote:
        vistos: set[int] = set()
        repetidos: set[int] = set()
        for p in self.precios:
            if p.insumo_id in vistos:
                repetidos.add(p.insumo_id)
            vistos.add(p.insumo_id)
        if repetidos:
            raise ValueError(f"Insumos repetidos en la carga: {sorted(repetidos)}")
        return self


class PreciosLoteResultado(BaseModel):
    creados: int
    actualizados: int


class PrecioOut(AuditFields):
    id: int
    insumo_id: int
    insumo_codigo: str
    insumo_descripcion: str
    unidad_codigo: str
    tipo: TipoInsumo
    precio: Decimal
    fuente: str | None = None

    @classmethod
    def desde(cls, p: PrecioInsumo, insumo: Insumo) -> PrecioOut:
        return cls(
            id=p.id,
            insumo_id=p.insumo_id,
            insumo_codigo=insumo.codigo,
            insumo_descripcion=insumo.descripcion,
            unidad_codigo=insumo.unidad.codigo,
            tipo=insumo.tipo,
            precio=p.precio,
            fuente=p.fuente,
            created_at=p.created_at,
            updated_at=p.updated_at,
            created_by=p.created_by,
            updated_by=p.updated_by,
        )


class PrecioVigenteOut(BaseModel):
    insumo_id: int
    precio: Decimal
    lista_id: int
    fecha_desde: date


# =========================================================================================
# Proyectos, etapas y torres
# =========================================================================================
class TorreCreate(_In):
    codigo: Codigo30
    nombre: Texto200
    numero_pisos: EnteroNoNegativo | None = None
    numero_unidades: EnteroNoNegativo | None = None


class TorreUpdate(_In):
    codigo: Codigo30 | None = None
    nombre: Texto200 | None = None
    numero_pisos: EnteroNoNegativo | None = None
    numero_unidades: EnteroNoNegativo | None = None


class TorreOut(AuditFields):
    id: int
    etapa_id: int
    codigo: str
    nombre: str
    numero_pisos: int | None = None
    numero_unidades: int | None = None


class EtapaCreate(_In):
    codigo: Codigo30
    nombre: Texto200
    orden: Int32 = 0
    numero_unidades: EnteroNoNegativo | None = None


class EtapaUpdate(_In):
    codigo: Codigo30 | None = None
    nombre: Texto200 | None = None
    orden: Int32 | None = None
    numero_unidades: EnteroNoNegativo | None = None


class EtapaOut(AuditFields):
    id: int
    proyecto_id: int
    codigo: str
    nombre: str
    orden: int
    numero_unidades: int | None = None
    torres: list[TorreOut] = []

    @classmethod
    def desde(cls, e: Etapa) -> EtapaOut:
        return cls(
            id=e.id,
            proyecto_id=e.proyecto_id,
            codigo=e.codigo,
            nombre=e.nombre,
            orden=e.orden,
            numero_unidades=e.numero_unidades,
            torres=[TorreOut.model_validate(t) for t in e.torres],
            created_at=e.created_at,
            updated_at=e.updated_at,
            created_by=e.created_by,
            updated_by=e.updated_by,
        )


class _FechasProyecto(_In):
    fecha_inicio: date | None = None
    fecha_fin_estimada: date | None = None

    @model_validator(mode="after")
    def _fechas_coherentes(self):  # type: ignore[no-untyped-def]
        if self.fecha_inicio and self.fecha_fin_estimada and self.fecha_fin_estimada < self.fecha_inicio:
            raise ValueError("fecha_fin_estimada no puede ser anterior a fecha_inicio")
        return self


class ProyectoCreate(_FechasProyecto):
    codigo: Codigo30
    nombre: Texto200
    ciudad_id: int
    tipo: TipoProyecto
    estado: EstadoProyecto = EstadoProyecto.PLANEACION
    numero_unidades: EnteroNoNegativo | None = None
    descripcion: TextoLibre | None = None


class ProyectoUpdate(_FechasProyecto):
    nombre: Texto200 | None = None
    ciudad_id: int | None = None
    tipo: TipoProyecto | None = None
    estado: EstadoProyecto | None = None
    numero_unidades: EnteroNoNegativo | None = None
    descripcion: TextoLibre | None = None


class ProyectoOut(AuditFields):
    id: int
    codigo: str
    nombre: str
    ciudad_id: int
    ciudad_codigo: str
    ciudad_nombre: str
    tipo: TipoProyecto
    estado: EstadoProyecto
    fecha_inicio: date | None = None
    fecha_fin_estimada: date | None = None
    numero_unidades: int | None = None
    descripcion: str | None = None

    @staticmethod
    def _campos(p: Proyecto) -> dict[str, object]:
        return {
            "id": p.id,
            "codigo": p.codigo,
            "nombre": p.nombre,
            "ciudad_id": p.ciudad_id,
            "ciudad_codigo": p.ciudad.codigo,
            "ciudad_nombre": p.ciudad.nombre,
            "tipo": p.tipo,
            "estado": p.estado,
            "fecha_inicio": p.fecha_inicio,
            "fecha_fin_estimada": p.fecha_fin_estimada,
            "numero_unidades": p.numero_unidades,
            "descripcion": p.descripcion,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "created_by": p.created_by,
            "updated_by": p.updated_by,
        }

    @classmethod
    def desde(cls, p: Proyecto) -> ProyectoOut:
        return cls(**cls._campos(p))  # type: ignore[arg-type]


class ProyectoDetalleOut(ProyectoOut):
    etapas: list[EtapaOut] = []

    @classmethod
    def desde(cls, p: Proyecto) -> ProyectoDetalleOut:
        return cls(**cls._campos(p), etapas=[EtapaOut.desde(e) for e in p.etapas])  # type: ignore[arg-type]


# =========================================================================================
# EDT presupuestal
# =========================================================================================
class EdtNodoCreate(_In):
    parent_id: int | None = None
    nivel: NivelEdt
    codigo: Codigo30
    descripcion: Texto300
    unidad_id: int | None = None
    orden: Int32 | None = None
    notas: TextoLibre | None = None

    @field_validator("codigo")
    @classmethod
    def _codigo_edt(cls, v: str) -> str:
        if ".." in v or v.endswith(".") or "_" in v or "-" in v:
            raise ValueError(
                "El código EDT solo admite segmentos alfanuméricos separados por punto (p. ej. 01.02.003)"
            )
        return v


class EdtNodoUpdate(_In):
    descripcion: Texto300 | None = None
    unidad_id: int | None = None
    orden: Int32 | None = None
    activo: bool | None = None
    notas: TextoLibre | None = None


class EdtNodoOut(AuditFields):
    id: int
    parent_id: int | None = None
    nivel: NivelEdt
    codigo: str
    descripcion: str
    unidad_id: int | None = None
    unidad_codigo: str | None = None
    orden: int
    activo: bool
    notas: str | None = None
    tiene_apu: bool = False

    @staticmethod
    def _campos(n: EdtNodo, tiene_apu: bool) -> dict[str, object]:
        return {
            "id": n.id,
            "parent_id": n.parent_id,
            "nivel": n.nivel,
            "codigo": n.codigo,
            "descripcion": n.descripcion,
            "unidad_id": n.unidad_id,
            "unidad_codigo": n.unidad.codigo if n.unidad is not None else None,
            "orden": n.orden,
            "activo": n.activo,
            "notas": n.notas,
            "tiene_apu": tiene_apu,
            "created_at": n.created_at,
            "updated_at": n.updated_at,
            "created_by": n.created_by,
            "updated_by": n.updated_by,
        }

    @classmethod
    def desde(cls, n: EdtNodo, tiene_apu: bool = False) -> EdtNodoOut:
        return cls(**cls._campos(n, tiene_apu))  # type: ignore[arg-type]


class EdtArbolNodo(EdtNodoOut):
    hijos: list[EdtArbolNodo] = []


class EdtRutaNodo(BaseModel):
    id: int
    nivel: NivelEdt
    codigo: str
    descripcion: str


class EdtNodoDetalleOut(EdtNodoOut):
    ruta: list[EdtRutaNodo] = []
