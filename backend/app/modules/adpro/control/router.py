"""Endpoints REST de ADPRO / control (prefijo final: /api/adpro/control).

Contrato: docs/API_CONTRATO.md (sección 5). Routers delgados: validan entrada, aplican roles y
delegan en ``service.py``. Lectura: cualquier usuario autenticado; escritura: ver contrato.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.schemas import Page
from app.core.security import (
    ROLES_ESCRITURA_CONTROL,
    ROLES_ESCRITURA_PRESUPUESTO,
    CurrentUser,
    require_role,
)
from app.modules.adpro.control import service
from app.modules.adpro.control.schemas import (
    PERIODO_PATTERN,
    ComparativoOut,
    CompromisoAnular,
    CompromisoCreate,
    CompromisoDetalleOut,
    CompromisoOut,
    CompromisoUpdate,
    EjecucionLote,
    EjecucionLoteResultado,
    EjecucionOut,
    ImportResultado,
    ModoImportacion,
    NivelComparativo,
    TableroFila,
    TableroOut,
)
from app.modules.adpro.enums import EstadoCompromiso, TipoCompromiso

router = APIRouter(prefix="/control", tags=["ADPRO - Control"])

Db = Annotated[Session, Depends(get_db)]
Periodo = Annotated[str | None, Query(pattern=PERIODO_PATTERN, description="YYYY-MM")]
ESCRITURA_CONTROL = [Depends(require_role(*ROLES_ESCRITURA_CONTROL))]
ESCRITURA_PRESUPUESTO = [Depends(require_role(*ROLES_ESCRITURA_PRESUPUESTO))]


def _excel(archivo: service.ArchivoExcel) -> Response:
    return Response(
        content=archivo.contenido,
        media_type=archivo.media_type,
        headers={"Content-Disposition": f'attachment; filename="{archivo.nombre}"'},
    )


# --- 5.1 Comparativo ---------------------------------------------------------------------
@router.get("/comparativo", response_model=ComparativoOut)
def comparativo(
    db: Db,
    _user: CurrentUser,
    version_base_id: int,
    version_comparada_id: int,
    nivel: NivelComparativo = "item",
) -> ComparativoOut:
    return service.comparar_versiones(db, version_base_id, version_comparada_id, nivel)


# --- 5.2 Compromisos ---------------------------------------------------------------------
@router.get("/compromisos", response_model=Page[CompromisoOut])
def listar_compromisos(
    db: Db,
    _user: CurrentUser,
    presupuesto_id: int | None = None,
    estado: EstadoCompromiso | None = None,
    tipo: TipoCompromiso | None = None,
    item_id: int | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CompromisoOut]:
    return service.listar_compromisos(
        db,
        presupuesto_id=presupuesto_id,
        estado=estado,
        tipo=tipo,
        item_id=item_id,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/compromisos",
    response_model=CompromisoDetalleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITURA_CONTROL,
)
def crear_compromiso(db: Db, data: CompromisoCreate) -> CompromisoDetalleOut:
    return service.crear_compromiso(db, data)


@router.get("/compromisos/{compromiso_id}", response_model=CompromisoDetalleOut)
def obtener_compromiso(db: Db, _user: CurrentUser, compromiso_id: int) -> CompromisoDetalleOut:
    return service.obtener_compromiso(db, compromiso_id)


@router.put(
    "/compromisos/{compromiso_id}", response_model=CompromisoDetalleOut, dependencies=ESCRITURA_CONTROL
)
def actualizar_compromiso(db: Db, compromiso_id: int, data: CompromisoUpdate) -> CompromisoDetalleOut:
    return service.actualizar_compromiso(db, compromiso_id, data)


@router.post(
    "/compromisos/{compromiso_id}/anular", response_model=CompromisoDetalleOut, dependencies=ESCRITURA_CONTROL
)
def anular_compromiso(db: Db, compromiso_id: int, data: CompromisoAnular) -> CompromisoDetalleOut:
    return service.anular_compromiso(db, compromiso_id, data.motivo)


@router.post(
    "/compromisos/{compromiso_id}/liquidar",
    response_model=CompromisoDetalleOut,
    dependencies=ESCRITURA_CONTROL,
)
def liquidar_compromiso(db: Db, compromiso_id: int) -> CompromisoDetalleOut:
    return service.liquidar_compromiso(db, compromiso_id)


# --- 5.3 Ejecución -----------------------------------------------------------------------
@router.get("/ejecucion/periodos", response_model=list[str])
def periodos(db: Db, _user: CurrentUser, presupuesto_id: int) -> list[str]:
    return service.listar_periodos(db, presupuesto_id)


@router.get("/ejecucion", response_model=list[EjecucionOut])
def listar_ejecucion(
    db: Db,
    _user: CurrentUser,
    presupuesto_id: int,
    periodo: Periodo = None,
    item_id: int | None = None,
    desde: Periodo = None,
    hasta: Periodo = None,
) -> list[EjecucionOut]:
    return service.listar_ejecucion(
        db, presupuesto_id=presupuesto_id, periodo=periodo, item_id=item_id, desde=desde, hasta=hasta
    )


@router.put("/ejecucion", response_model=EjecucionLoteResultado, dependencies=ESCRITURA_CONTROL)
def guardar_ejecucion(db: Db, data: EjecucionLote) -> EjecucionLoteResultado:
    return service.guardar_ejecucion(db, data)


@router.delete(
    "/ejecucion/{ejecucion_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ESCRITURA_CONTROL
)
def eliminar_ejecucion(db: Db, ejecucion_id: int) -> Response:
    service.eliminar_ejecucion(db, ejecucion_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 5.4 Tablero -------------------------------------------------------------------------
@router.get("/tablero/items", response_model=list[TableroFila])
def tablero_items(
    db: Db,
    _user: CurrentUser,
    presupuesto_id: int,
    version_id: int | None = None,
    capitulo_id: int | None = None,
    periodo_hasta: Periodo = None,
) -> list[TableroFila]:
    return service.tablero_items(db, presupuesto_id, version_id, capitulo_id, periodo_hasta)


@router.get("/tablero", response_model=TableroOut)
def tablero(
    db: Db,
    _user: CurrentUser,
    presupuesto_id: int,
    version_id: int | None = None,
    periodo_hasta: Periodo = None,
) -> TableroOut:
    return service.tablero(db, presupuesto_id, version_id, periodo_hasta)


# --- 5.5 Excel ---------------------------------------------------------------------------
@router.get("/excel/plantilla-presupuesto", response_class=Response)
def plantilla_presupuesto(db: Db, _user: CurrentUser) -> Response:
    return _excel(service.plantilla_presupuesto(db))


@router.get("/excel/comparativo", response_class=Response)
def excel_comparativo(
    db: Db,
    _user: CurrentUser,
    version_base_id: int,
    version_comparada_id: int,
    nivel: NivelComparativo = "item",
) -> Response:
    return _excel(service.exportar_comparativo(db, version_base_id, version_comparada_id, nivel))


@router.post(
    "/excel/presupuesto/{version_id}/importar",
    response_model=ImportResultado,
    dependencies=ESCRITURA_PRESUPUESTO,
)
def importar_presupuesto(
    db: Db,
    version_id: int,
    file: Annotated[UploadFile, File(description="Plantilla .xlsx")],
    modo: ModoImportacion = "agregar",
) -> ImportResultado:
    # Endpoint síncrono (corre en threadpool): la sesión SQLAlchemy es bloqueante.
    contenido = file.file.read(service.MAX_BYTES_IMPORTACION + 1)
    return service.importar_presupuesto(db, version_id, contenido, modo=modo, nombre_archivo=file.filename)


@router.get("/excel/presupuesto/{version_id}", response_class=Response)
def excel_presupuesto(db: Db, _user: CurrentUser, version_id: int) -> Response:
    return _excel(service.exportar_presupuesto(db, version_id))


@router.get("/excel/explosion/{version_id}", response_class=Response)
def excel_explosion(db: Db, _user: CurrentUser, version_id: int) -> Response:
    return _excel(service.exportar_explosion(db, version_id))
