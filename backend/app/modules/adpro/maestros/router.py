"""Endpoints REST de ADPRO / maestros (prefijo final: /api/adpro/maestros).

Contrato: docs/API_CONTRATO.md (sección maestros). Reglas:
- Routers delgados: validan entrada (schemas), aplican roles (``require_role``) y delegan en
  ``service.py``. Nada de lógica de negocio aquí.
- Lectura: cualquier usuario autenticado (``CurrentUser``). Escritura: ver roles del contrato.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import BusinessRuleError
from app.core.schemas import Page
from app.core.security import ROLES_ESCRITURA_MAESTROS, CurrentUser, require_role
from app.modules.adpro.enums import EstadoProyecto, NivelEdt, TipoInsumo, TipoProyecto

from . import schemas as s
from . import service

router = APIRouter(prefix="/maestros", tags=["ADPRO - Maestros"])

DB = Annotated[Session, Depends(get_db)]
ESCRITURA = [Depends(require_role(*ROLES_ESCRITURA_MAESTROS))]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


# =========================================================================================
# Unidades
# =========================================================================================
@router.get("/unidades", response_model=list[s.UnidadOut])
def listar_unidades(db: DB, _u: CurrentUser, q: str | None = None, activo: bool | None = None):
    return service.listar_unidades(db, q=q, activo=activo)


@router.post(
    "/unidades", response_model=s.UnidadOut, status_code=status.HTTP_201_CREATED, dependencies=ESCRITURA
)
def crear_unidad(data: s.UnidadCreate, db: DB):
    return service.crear_unidad(db, data)


@router.put("/unidades/{unidad_id}", response_model=s.UnidadOut, dependencies=ESCRITURA)
def actualizar_unidad(unidad_id: int, data: s.UnidadUpdate, db: DB):
    return service.actualizar_unidad(db, unidad_id, data)


# =========================================================================================
# Ciudades
# =========================================================================================
@router.get("/ciudades", response_model=list[s.CiudadOut])
def listar_ciudades(db: DB, _u: CurrentUser, q: str | None = None, activo: bool | None = None):
    return service.listar_ciudades(db, q=q, activo=activo)


@router.post(
    "/ciudades", response_model=s.CiudadOut, status_code=status.HTTP_201_CREATED, dependencies=ESCRITURA
)
def crear_ciudad(data: s.CiudadCreate, db: DB):
    return service.crear_ciudad(db, data)


@router.put("/ciudades/{ciudad_id}", response_model=s.CiudadOut, dependencies=ESCRITURA)
def actualizar_ciudad(ciudad_id: int, data: s.CiudadUpdate, db: DB):
    return service.actualizar_ciudad(db, ciudad_id, data)


# =========================================================================================
# Insumos
# =========================================================================================
@router.get("/insumos", response_model=Page[s.InsumoOut])
def listar_insumos(
    db: DB,
    _u: CurrentUser,
    q: str | None = None,
    tipo: TipoInsumo | None = None,
    activo: bool | None = None,
    unidad_id: int | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[s.InsumoOut]:
    items, total = service.listar_insumos(
        db, q=q, tipo=tipo, activo=activo, unidad_id=unidad_id, limit=limit, offset=offset
    )
    return Page(items=[s.InsumoOut.desde(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/insumos/{insumo_id}", response_model=s.InsumoOut)
def obtener_insumo(insumo_id: int, db: DB, _u: CurrentUser) -> s.InsumoOut:
    return s.InsumoOut.desde(service.obtener_insumo(db, insumo_id))


@router.post(
    "/insumos", response_model=s.InsumoOut, status_code=status.HTTP_201_CREATED, dependencies=ESCRITURA
)
def crear_insumo(data: s.InsumoCreate, db: DB) -> s.InsumoOut:
    return s.InsumoOut.desde(service.crear_insumo(db, data))


@router.put("/insumos/{insumo_id}", response_model=s.InsumoOut, dependencies=ESCRITURA)
def actualizar_insumo(insumo_id: int, data: s.InsumoUpdate, db: DB) -> s.InsumoOut:
    return s.InsumoOut.desde(service.actualizar_insumo(db, insumo_id, data))


@router.get("/insumos/{insumo_id}/precios", response_model=list[s.PrecioHistoricoOut])
def historico_precios(
    insumo_id: int, db: DB, _u: CurrentUser, ciudad_id: int | None = None
) -> list[s.PrecioHistoricoOut]:
    return service.historico_precios_insumo(db, insumo_id, ciudad_id=ciudad_id)


# =========================================================================================
# Listas de precios
# =========================================================================================
@router.get("/listas-precios", response_model=list[s.ListaPreciosOut])
def listar_listas(
    db: DB, _u: CurrentUser, ciudad_id: int | None = None, activo: bool | None = None
) -> list[s.ListaPreciosOut]:
    return service.listar_listas(db, ciudad_id=ciudad_id, activo=activo)


@router.post(
    "/listas-precios",
    response_model=s.ListaPreciosOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITURA,
)
def crear_lista(data: s.ListaPreciosCreate, db: DB) -> s.ListaPreciosOut:
    return service.lista_out(db, service.crear_lista(db, data))


@router.get("/listas-precios/{lista_id}", response_model=s.ListaPreciosOut)
def obtener_lista(lista_id: int, db: DB, _u: CurrentUser) -> s.ListaPreciosOut:
    return service.lista_out(db, service.obtener_lista(db, lista_id))


@router.put("/listas-precios/{lista_id}", response_model=s.ListaPreciosOut, dependencies=ESCRITURA)
def actualizar_lista(lista_id: int, data: s.ListaPreciosUpdate, db: DB) -> s.ListaPreciosOut:
    return service.lista_out(db, service.actualizar_lista(db, lista_id, data))


@router.get("/listas-precios/{lista_id}/precios", response_model=Page[s.PrecioOut])
def listar_precios_lista(
    lista_id: int,
    db: DB,
    _u: CurrentUser,
    q: str | None = None,
    tipo: TipoInsumo | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[s.PrecioOut]:
    items, total = service.listar_precios_lista(db, lista_id, q=q, tipo=tipo, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.put(
    "/listas-precios/{lista_id}/precios", response_model=s.PreciosLoteResultado, dependencies=ESCRITURA
)
def cargar_precios(lista_id: int, data: s.PreciosLote, db: DB) -> s.PreciosLoteResultado:
    return service.cargar_precios(db, lista_id, data)


@router.delete(
    "/listas-precios/{lista_id}/precios/{insumo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=ESCRITURA,
)
def eliminar_precio(lista_id: int, insumo_id: int, db: DB) -> Response:
    service.eliminar_precio(db, lista_id, insumo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/precios-vigentes", response_model=list[s.PrecioVigenteOut])
def precios_vigentes(
    db: DB,
    _u: CurrentUser,
    ciudad_id: int,
    insumo_ids: Annotated[str, Query(description="IDs separados por coma, p. ej. 1,2,3")],
    fecha: date | None = None,
) -> list[s.PrecioVigenteOut]:
    try:
        ids = [int(x) for x in insumo_ids.split(",") if x.strip()]
    except ValueError as exc:
        raise BusinessRuleError(
            "insumo_ids debe ser una lista de enteros separados por coma (p. ej. 1,2,3)"
        ) from exc
    fecha_consulta = fecha or date.today()
    return [
        s.PrecioVigenteOut(
            insumo_id=p.insumo_id, precio=p.precio, lista_id=p.lista_id, fecha_desde=p.fecha_desde
        )
        for p in service.precios_vigentes(db, ciudad_id, fecha_consulta, ids)
    ]


# =========================================================================================
# Proyectos, etapas y torres
# =========================================================================================
@router.get("/proyectos", response_model=list[s.ProyectoOut])
def listar_proyectos(
    db: DB,
    _u: CurrentUser,
    q: str | None = None,
    estado: EstadoProyecto | None = None,
    tipo: TipoProyecto | None = None,
    ciudad_id: int | None = None,
) -> list[s.ProyectoOut]:
    proyectos = service.listar_proyectos(db, q=q, estado=estado, tipo=tipo, ciudad_id=ciudad_id)
    return [s.ProyectoOut.desde(p) for p in proyectos]


@router.post(
    "/proyectos",
    response_model=s.ProyectoDetalleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITURA,
)
def crear_proyecto(data: s.ProyectoCreate, db: DB) -> s.ProyectoDetalleOut:
    return s.ProyectoDetalleOut.desde(service.crear_proyecto(db, data))


@router.get("/proyectos/{proyecto_id}", response_model=s.ProyectoDetalleOut)
def obtener_proyecto(proyecto_id: int, db: DB, _u: CurrentUser) -> s.ProyectoDetalleOut:
    return s.ProyectoDetalleOut.desde(service.obtener_proyecto(db, proyecto_id))


@router.put("/proyectos/{proyecto_id}", response_model=s.ProyectoDetalleOut, dependencies=ESCRITURA)
def actualizar_proyecto(proyecto_id: int, data: s.ProyectoUpdate, db: DB) -> s.ProyectoDetalleOut:
    return s.ProyectoDetalleOut.desde(service.actualizar_proyecto(db, proyecto_id, data))


@router.post(
    "/proyectos/{proyecto_id}/etapas",
    response_model=s.EtapaOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITURA,
)
def crear_etapa(proyecto_id: int, data: s.EtapaCreate, db: DB) -> s.EtapaOut:
    return s.EtapaOut.desde(service.crear_etapa(db, proyecto_id, data))


@router.put("/etapas/{etapa_id}", response_model=s.EtapaOut, dependencies=ESCRITURA)
def actualizar_etapa(etapa_id: int, data: s.EtapaUpdate, db: DB) -> s.EtapaOut:
    return s.EtapaOut.desde(service.actualizar_etapa(db, etapa_id, data))


@router.delete(
    "/etapas/{etapa_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=ESCRITURA,
)
def eliminar_etapa(etapa_id: int, db: DB) -> Response:
    service.eliminar_etapa(db, etapa_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/etapas/{etapa_id}/torres",
    response_model=s.TorreOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITURA,
)
def crear_torre(etapa_id: int, data: s.TorreCreate, db: DB) -> s.TorreOut:
    return s.TorreOut.model_validate(service.crear_torre(db, etapa_id, data))


@router.put("/torres/{torre_id}", response_model=s.TorreOut, dependencies=ESCRITURA)
def actualizar_torre(torre_id: int, data: s.TorreUpdate, db: DB) -> s.TorreOut:
    return s.TorreOut.model_validate(service.actualizar_torre(db, torre_id, data))


@router.delete(
    "/torres/{torre_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=ESCRITURA,
)
def eliminar_torre(torre_id: int, db: DB) -> Response:
    service.eliminar_torre(db, torre_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================================================
# EDT presupuestal (rutas estáticas antes de /edt/{id})
# =========================================================================================
@router.get("/edt", response_model=Page[s.EdtNodoOut])
def listar_edt(
    db: DB,
    _u: CurrentUser,
    nivel: NivelEdt | None = None,
    parent_id: int | None = None,
    q: str | None = None,
    activo: bool | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[s.EdtNodoOut]:
    items, total = service.listar_edt(
        db, nivel=nivel, parent_id=parent_id, q=q, activo=activo, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/edt/arbol", response_model=list[s.EdtArbolNodo])
def arbol_edt(
    db: DB,
    _u: CurrentUser,
    capitulo_id: int | None = None,
    hasta_nivel: NivelEdt = NivelEdt.ITEM,
    activo: bool | None = None,
) -> list[s.EdtArbolNodo]:
    return service.arbol_edt(db, capitulo_id=capitulo_id, hasta_nivel=hasta_nivel, activo=activo)


@router.get("/edt/{nodo_id}", response_model=s.EdtNodoDetalleOut)
def obtener_edt(nodo_id: int, db: DB, _u: CurrentUser) -> s.EdtNodoDetalleOut:
    return service.detalle_edt(db, nodo_id)


@router.post("/edt", response_model=s.EdtNodoOut, status_code=status.HTTP_201_CREATED, dependencies=ESCRITURA)
def crear_edt(data: s.EdtNodoCreate, db: DB) -> s.EdtNodoOut:
    return service.edt_out(db, service.crear_edt_nodo(db, data))


@router.put("/edt/{nodo_id}", response_model=s.EdtNodoOut, dependencies=ESCRITURA)
def actualizar_edt(nodo_id: int, data: s.EdtNodoUpdate, db: DB) -> s.EdtNodoOut:
    return service.edt_out(db, service.actualizar_edt_nodo(db, nodo_id, data))
