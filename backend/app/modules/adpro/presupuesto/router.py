"""Endpoints REST de ADPRO / presupuesto (prefijo final: /api/adpro/presupuestos).

Contrato: docs/API_CONTRATO.md §4. Routers delgados: validan entrada (schemas), aplican roles
(``require_role``) y delegan en ``service.py``. Lectura: cualquier usuario autenticado.
Escritura: rol P (admin, presupuesto). Aprobar/cerrar: rol A (admin).
Las rutas ``/versiones/...`` se declaran ANTES de ``/{presupuesto_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import ROLES_APROBACION, ROLES_ESCRITURA_PRESUPUESTO, CurrentUser, require_role
from app.modules.adpro.enums import TipoInsumo

from . import schemas as s
from . import service

router = APIRouter(prefix="/presupuestos", tags=["ADPRO - Presupuesto"])

DB = Annotated[Session, Depends(get_db)]
ESCRITURA = [Depends(require_role(*ROLES_ESCRITURA_PRESUPUESTO))]
APROBACION = [Depends(require_role(*ROLES_APROBACION))]
CREADO = status.HTTP_201_CREATED


# =====================================================================================
# Versiones (rutas estáticas primero)
# =====================================================================================
@router.get("/versiones/{vid}", response_model=s.VersionOut)
def obtener_version(vid: int, db: DB, _user: CurrentUser) -> s.VersionOut:
    return service.version_out(db, service.obtener_version(db, vid))


@router.put("/versiones/{vid}", response_model=s.VersionOut, dependencies=ESCRITURA)
def actualizar_version(vid: int, data: s.VersionUpdate, db: DB) -> s.VersionOut:
    return service.version_out(db, service.actualizar_version(db, vid, data))


@router.delete("/versiones/{vid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ESCRITURA)
def eliminar_version(vid: int, db: DB) -> Response:
    service.eliminar_version(db, vid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/versiones/{vid}/aprobar", response_model=s.VersionOut, dependencies=APROBACION)
def aprobar_version(vid: int, db: DB, data: s.TransicionIn | None = None) -> s.VersionOut:
    obs = data.observacion if data else None
    return service.version_out(db, service.aprobar_version(db, vid, obs))


@router.post("/versiones/{vid}/cerrar", response_model=s.VersionOut, dependencies=APROBACION)
def cerrar_version(vid: int, db: DB, data: s.TransicionIn | None = None) -> s.VersionOut:
    obs = data.observacion if data else None
    return service.version_out(db, service.cerrar_version(db, vid, obs))


@router.post(
    "/versiones/{vid}/copiar", response_model=s.VersionOut, status_code=CREADO, dependencies=ESCRITURA
)
def copiar_version(vid: int, data: s.VersionCopy, db: DB) -> s.VersionOut:
    return service.version_out(db, service.copiar_version(db, vid, data))


@router.post("/versiones/{vid}/recalcular", response_model=s.RecalculoOut, dependencies=ESCRITURA)
def recalcular_version(vid: int, db: DB) -> s.RecalculoOut:
    return service.recalcular_version(db, vid)


@router.get("/versiones/{vid}/resumen", response_model=s.ResumenOut)
def resumen(vid: int, db: DB, _user: CurrentUser) -> s.ResumenOut:
    return service.calcular_resumen(db, vid)


@router.get("/versiones/{vid}/explosion", response_model=s.ExplosionOut)
def explosion(vid: int, db: DB, _user: CurrentUser, tipo: TipoInsumo | None = None) -> s.ExplosionOut:
    return service.calcular_explosion(db, vid, tipo)


# --- Líneas ------------------------------------------------------------------------------
@router.get("/versiones/{vid}/lineas", response_model=list[s.LineaOut])
def listar_lineas(
    vid: int, db: DB, _user: CurrentUser, capitulo_id: int | None = None, q: str | None = None
) -> list[s.LineaOut]:
    return service.listar_lineas(db, vid, capitulo_id=capitulo_id, q=q)


@router.post("/versiones/{vid}/lineas/lote", response_model=s.LoteResultado, dependencies=ESCRITURA)
def crear_lineas_lote(vid: int, data: s.LineasLote, db: DB) -> s.LoteResultado:
    return service.crear_lineas_lote(db, vid, data.lineas)


@router.post("/versiones/{vid}/lineas", response_model=s.LineaOut, status_code=CREADO, dependencies=ESCRITURA)
def crear_linea(vid: int, data: s.LineaCreate, db: DB) -> s.LineaOut:
    return service.linea_out(db, service.crear_linea(db, vid, data))


@router.put("/versiones/{vid}/lineas/{lid}", response_model=s.LineaOut, dependencies=ESCRITURA)
def actualizar_linea(vid: int, lid: int, data: s.LineaUpdate, db: DB) -> s.LineaOut:
    return service.linea_out(db, service.actualizar_linea(db, vid, lid, data))


@router.delete(
    "/versiones/{vid}/lineas/{lid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ESCRITURA
)
def eliminar_linea(vid: int, lid: int, db: DB) -> Response:
    service.eliminar_linea(db, vid, lid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/versiones/{vid}/lineas/{lid}/insumos", response_model=list[s.LineaInsumoOut])
def listar_insumos_linea(vid: int, lid: int, db: DB, _user: CurrentUser) -> list[s.LineaInsumoOut]:
    return service.listar_insumos_linea(db, vid, lid)


# =====================================================================================
# Presupuestos
# =====================================================================================
@router.get("", response_model=list[s.PresupuestoOut])
def listar_presupuestos(
    db: DB, _user: CurrentUser, proyecto_id: int | None = None, q: str | None = None
) -> list[s.PresupuestoOut]:
    return [service.presupuesto_out(p) for p in service.listar_presupuestos(db, proyecto_id=proyecto_id, q=q)]


@router.post("", response_model=s.PresupuestoDetalleOut, status_code=CREADO, dependencies=ESCRITURA)
def crear_presupuesto(data: s.PresupuestoCreate, db: DB) -> s.PresupuestoDetalleOut:
    return service.presupuesto_detalle_out(db, service.crear_presupuesto(db, data))


@router.get("/{presupuesto_id}", response_model=s.PresupuestoDetalleOut)
def obtener_presupuesto(presupuesto_id: int, db: DB, _user: CurrentUser) -> s.PresupuestoDetalleOut:
    return service.presupuesto_detalle_out(db, service.obtener_presupuesto(db, presupuesto_id))


@router.put("/{presupuesto_id}", response_model=s.PresupuestoDetalleOut, dependencies=ESCRITURA)
def actualizar_presupuesto(presupuesto_id: int, data: s.PresupuestoUpdate, db: DB) -> s.PresupuestoDetalleOut:
    return service.presupuesto_detalle_out(db, service.actualizar_presupuesto(db, presupuesto_id, data))


@router.post(
    "/{presupuesto_id}/versiones", response_model=s.VersionOut, status_code=CREADO, dependencies=ESCRITURA
)
def crear_version(presupuesto_id: int, data: s.VersionCreate, db: DB) -> s.VersionOut:
    return service.version_out(db, service.crear_version(db, presupuesto_id, data))
