"""Endpoints REST de ADPRO / apu (prefijo final: /api/adpro/apu).

Contrato: docs/API_CONTRATO.md §3. Routers delgados: validan entrada (schemas), aplican roles
(``require_role``) y delegan en ``service.py``. Lectura: cualquier usuario autenticado
(``CurrentUser``). Escritura: rol M (admin, presupuesto).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.schemas import Page
from app.core.security import ROLES_ESCRITURA_MAESTROS, CurrentUser, require_role

from . import schemas as s
from . import service

router = APIRouter(prefix="/apu", tags=["ADPRO - APU"])

DB = Annotated[Session, Depends(get_db)]
ESCRITURA = [Depends(require_role(*ROLES_ESCRITURA_MAESTROS))]


@router.get("/apus", response_model=Page[s.ApuOut])
def listar_apus(
    db: DB,
    _user: CurrentUser,
    q: str | None = None,
    capitulo_id: int | None = None,
    activo: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[s.ApuOut]:
    rows, total = service.listar_apus(
        db, q=q, capitulo_id=capitulo_id, activo=activo, limit=limit, offset=offset
    )
    return Page(items=[service.apu_out(a) for a in rows], total=total, limit=limit, offset=offset)


# Ruta estática ANTES de /apus/{apu_id}
@router.get("/apus/por-item/{item_id}", response_model=s.ApuDetalleOut)
def obtener_apu_por_item(item_id: int, db: DB, _user: CurrentUser) -> s.ApuDetalleOut:
    return service.apu_detalle_out(service.obtener_apu_por_item(db, item_id))


@router.get("/apus/{apu_id}", response_model=s.ApuDetalleOut)
def obtener_apu(apu_id: int, db: DB, _user: CurrentUser) -> s.ApuDetalleOut:
    return service.apu_detalle_out(service.obtener_apu(db, apu_id))


@router.post(
    "/apus", response_model=s.ApuDetalleOut, status_code=status.HTTP_201_CREATED, dependencies=ESCRITURA
)
def crear_apu(data: s.ApuCreate, db: DB) -> s.ApuDetalleOut:
    return service.apu_detalle_out(service.crear_apu(db, data))


@router.put("/apus/{apu_id}", response_model=s.ApuDetalleOut, dependencies=ESCRITURA)
def actualizar_apu(apu_id: int, data: s.ApuUpdate, db: DB) -> s.ApuDetalleOut:
    return service.apu_detalle_out(service.actualizar_apu(db, apu_id, data))


@router.put("/apus/{apu_id}/insumos", response_model=s.ApuDetalleOut, dependencies=ESCRITURA)
def reemplazar_insumos(apu_id: int, data: s.ApuInsumosReemplazo, db: DB) -> s.ApuDetalleOut:
    return service.apu_detalle_out(service.reemplazar_insumos(db, apu_id, data.insumos))


@router.post(
    "/apus/{apu_id}/insumos",
    response_model=s.ApuInsumoOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITURA,
)
def agregar_insumo(apu_id: int, data: s.ApuInsumoIn, db: DB) -> s.ApuInsumoOut:
    return service.apu_insumo_out(service.agregar_insumo(db, apu_id, data))


@router.put("/apus/{apu_id}/insumos/{apu_insumo_id}", response_model=s.ApuInsumoOut, dependencies=ESCRITURA)
def actualizar_insumo(apu_id: int, apu_insumo_id: int, data: s.ApuInsumoUpdate, db: DB) -> s.ApuInsumoOut:
    return service.apu_insumo_out(service.actualizar_insumo(db, apu_id, apu_insumo_id, data))


@router.delete(
    "/apus/{apu_id}/insumos/{apu_insumo_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ESCRITURA
)
def eliminar_insumo(apu_id: int, apu_insumo_id: int, db: DB) -> Response:
    service.eliminar_insumo(db, apu_id, apu_insumo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/apus/{apu_id}/copiar",
    response_model=s.ApuDetalleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITURA,
)
def copiar_apu(apu_id: int, data: s.ApuCopia, db: DB) -> s.ApuDetalleOut:
    return service.apu_detalle_out(service.copiar_apu(db, apu_id, data))


@router.get("/apus/{apu_id}/valorizacion", response_model=s.ValorizacionOut)
def valorizar_apu(
    apu_id: int,
    db: DB,
    _user: CurrentUser,
    ciudad_id: int,
    fecha: date | None = None,
) -> s.ValorizacionOut:
    return service.valorizar(db, apu_id, ciudad_id, fecha)
