"""Consulta de precios vigentes y valorización de APU (compartido por apu y presupuesto).

PROPIEDAD: agente ARQUITECTO. Contrato interno estable:

- ``precios_vigentes(db, insumo_ids, ciudad_id, fecha) -> dict[int, PrecioVigente]``
- ``precio_vigente(db, insumo_id, ciudad_id, fecha) -> PrecioVigente | None``
- ``valorizar_apu(db, apu, ciudad_id, fecha) -> ValorizacionApu``

Regla de precio vigente: para cada insumo se toma el precio de la lista ACTIVA de la ciudad con
la mayor ``fecha_desde`` <= ``fecha`` que contenga ese insumo (si la lista más reciente no lo
trae, se usa el de la lista anterior). Si no hay precio, el componente se marca
``precio_faltante=True`` y aporta 0.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.adpro.calculos import ZERO, q4, valor_componente
from app.modules.adpro.models import Apu, ListaPrecios, PrecioInsumo


@dataclass(frozen=True)
class PrecioVigente:
    insumo_id: int
    precio: Decimal
    lista_id: int
    fecha_desde: date


@dataclass(frozen=True)
class ComponenteValorizado:
    insumo_id: int
    cantidad: Decimal
    desperdicio_pct: Decimal
    precio_unitario: Decimal
    valor_unitario: Decimal  # aporte al valor unitario del ítem
    precio_faltante: bool
    lista_id: int | None


@dataclass
class ValorizacionApu:
    apu_id: int
    item_id: int
    ciudad_id: int
    fecha: date
    valor_unitario: Decimal = ZERO
    componentes: list[ComponenteValorizado] = field(default_factory=list)

    @property
    def insumos_sin_precio(self) -> list[int]:
        return [c.insumo_id for c in self.componentes if c.precio_faltante]


def precios_vigentes(
    db: Session, insumo_ids: Iterable[int], ciudad_id: int, fecha: date
) -> dict[int, PrecioVigente]:
    ids = sorted(set(insumo_ids))
    if not ids:
        return {}
    stmt = (
        select(PrecioInsumo.insumo_id, PrecioInsumo.precio, ListaPrecios.id, ListaPrecios.fecha_desde)
        .join(ListaPrecios, ListaPrecios.id == PrecioInsumo.lista_id)
        .where(
            ListaPrecios.ciudad_id == ciudad_id,
            ListaPrecios.activo.is_(True),
            ListaPrecios.fecha_desde <= fecha,
            PrecioInsumo.insumo_id.in_(ids),
        )
        .order_by(PrecioInsumo.insumo_id, ListaPrecios.fecha_desde.desc())
    )
    out: dict[int, PrecioVigente] = {}
    for insumo_id, precio, lista_id, fecha_desde in db.execute(stmt):
        if insumo_id not in out:
            out[insumo_id] = PrecioVigente(insumo_id, Decimal(precio), lista_id, fecha_desde)
    return out


def precio_vigente(db: Session, insumo_id: int, ciudad_id: int, fecha: date) -> PrecioVigente | None:
    return precios_vigentes(db, [insumo_id], ciudad_id, fecha).get(insumo_id)


def valorizar_apu(db: Session, apu: Apu, ciudad_id: int, fecha: date) -> ValorizacionApu:
    precios = precios_vigentes(db, (c.insumo_id for c in apu.insumos), ciudad_id, fecha)
    res = ValorizacionApu(apu_id=apu.id, item_id=apu.item_id, ciudad_id=ciudad_id, fecha=fecha)
    total = ZERO
    for comp in apu.insumos:
        pv = precios.get(comp.insumo_id)
        precio = pv.precio if pv else ZERO
        valor = valor_componente(comp.cantidad, comp.desperdicio_pct, precio)
        total += valor
        res.componentes.append(
            ComponenteValorizado(
                insumo_id=comp.insumo_id,
                cantidad=comp.cantidad,
                desperdicio_pct=comp.desperdicio_pct,
                precio_unitario=q4(precio),
                valor_unitario=valor,
                precio_faltante=pv is None,
                lista_id=pv.lista_id if pv else None,
            )
        )
    res.valor_unitario = q4(total)
    return res
