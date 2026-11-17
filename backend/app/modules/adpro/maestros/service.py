"""Lógica de negocio de ADPRO / maestros.

Funciones puras respecto a HTTP: reciben ``db: Session`` y datos validados, devuelven modelos
o dataclasses, y lanzan ``app.core.errors`` (NotFoundError, ConflictError, BusinessRuleError).
Hacen ``db.commit()`` al final de cada operación de escritura y registran auditoría con
``app.core.audit.registrar_auditoria`` en operaciones relevantes.
Fórmulas: usar SIEMPRE ``app.modules.adpro.calculos`` y ``app.modules.adpro.valorizacion``.

API pública reutilizable por otros submódulos (estable):

- ``precio_vigente(db, insumo_id, fecha, ciudad_id) -> PrecioVigente | None``
- ``precios_vigentes(db, ciudad_id, fecha, insumo_ids) -> list[PrecioVigente]``
- ``obtener_insumo / obtener_ciudad / obtener_unidad / obtener_proyecto / obtener_etapa /
  obtener_edt_nodo(db, id)`` (404 si no existe)
- ``obtener_item_edt(db, item_id)`` (404 si no existe; 422 si el nodo no es nivel ITEM)
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import Accion, registrar_auditoria
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.query import contiene
from app.modules.adpro import valorizacion
from app.modules.adpro.enums import EstadoVersion, NivelEdt, TipoInsumo
from app.modules.adpro.models import (
    Apu,
    ApuInsumo,
    Ciudad,
    CompromisoLinea,
    EdtNodo,
    Etapa,
    Insumo,
    ListaPrecios,
    PrecioInsumo,
    Presupuesto,
    PresupuestoLinea,
    PresupuestoLineaInsumo,
    PresupuestoVersion,
    Proyecto,
    Torre,
    Unidad,
)
from app.modules.adpro.valorizacion import PrecioVigente

from . import schemas as s

M = TypeVar("M")


# =========================================================================================
# Utilidades internas
# =========================================================================================
def _get(db: Session, model: type[M], obj_id: int, nombre: str) -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFoundError(f"{nombre} con id {obj_id} no existe", details={"id": obj_id})
    return obj


def _cambios(data: BaseModel) -> dict[str, Any]:
    """Campos efectivamente enviados en un PUT parcial."""
    return data.model_dump(exclude_unset=True)


def _aplicar(obj: Any, cambios: dict[str, Any]) -> None:
    for k, v in cambios.items():
        setattr(obj, k, v)


def _aplicar_auditado(db: Session, obj: Any, cambios: dict[str, Any], entidad: str) -> None:
    """Aplica ``cambios`` y registra ACTUALIZAR con antes/después de los campos que cambian."""
    diff = {k: {"antes": getattr(obj, k), "despues": v} for k, v in cambios.items() if getattr(obj, k) != v}
    _aplicar(obj, cambios)
    if diff:
        registrar_auditoria(
            db, accion=Accion.ACTUALIZAR, entidad=entidad, entidad_id=obj.id, detalle={"cambios": diff}
        )


def _commit(db: Session, obj: Any) -> None:
    db.commit()
    db.refresh(obj)


def _ref_activa(db: Session, model: type[M], obj_id: int, nombre: str) -> M:
    """Referencia desde el cuerpo de la petición: debe existir y estar activa (422)."""
    obj = db.get(model, obj_id)
    if obj is None:
        raise BusinessRuleError(f"{nombre} con id {obj_id} no existe", details={"id": obj_id})
    if not getattr(obj, "activo", True):
        codigo = getattr(obj, "codigo", obj_id)
        raise BusinessRuleError(f"{nombre} '{codigo}' está inactiva", details={"id": obj_id})
    return obj


def _codigo_unico(db: Session, model: Any, codigo: str, nombre: str, excluir_id: int | None = None) -> None:
    stmt = select(model.id).where(model.codigo == codigo)
    if excluir_id is not None:
        stmt = stmt.where(model.id != excluir_id)
    if db.scalar(stmt) is not None:
        raise ConflictError(f"Ya existe {nombre} con código '{codigo}'", details={"codigo": codigo})


# =========================================================================================
# Unidades
# =========================================================================================
def obtener_unidad(db: Session, unidad_id: int) -> Unidad:
    return _get(db, Unidad, unidad_id, "Unidad")


def listar_unidades(db: Session, *, q: str | None = None, activo: bool | None = None) -> list[Unidad]:
    stmt = select(Unidad)
    if q:
        stmt = stmt.where(or_(contiene(Unidad.codigo, q), contiene(Unidad.nombre, q)))
    if activo is not None:
        stmt = stmt.where(Unidad.activo.is_(activo))
    return list(db.scalars(stmt.order_by(Unidad.codigo)))


def crear_unidad(db: Session, data: s.UnidadCreate) -> Unidad:
    _codigo_unico(db, Unidad, data.codigo, "una unidad")
    unidad = Unidad(**data.model_dump())
    db.add(unidad)
    _commit(db, unidad)
    return unidad


def actualizar_unidad(db: Session, unidad_id: int, data: s.UnidadUpdate) -> Unidad:
    unidad = obtener_unidad(db, unidad_id)
    cambios = _cambios(data)
    if cambios.get("codigo") and cambios["codigo"] != unidad.codigo:
        _codigo_unico(db, Unidad, cambios["codigo"], "una unidad", excluir_id=unidad.id)
    _aplicar_auditado(db, unidad, {k: v for k, v in cambios.items() if v is not None}, "unidad")
    _commit(db, unidad)
    return unidad


# =========================================================================================
# Ciudades
# =========================================================================================
def obtener_ciudad(db: Session, ciudad_id: int) -> Ciudad:
    return _get(db, Ciudad, ciudad_id, "Ciudad")


def listar_ciudades(db: Session, *, q: str | None = None, activo: bool | None = None) -> list[Ciudad]:
    stmt = select(Ciudad)
    if q:
        stmt = stmt.where(or_(contiene(Ciudad.codigo, q), contiene(Ciudad.nombre, q)))
    if activo is not None:
        stmt = stmt.where(Ciudad.activo.is_(activo))
    return list(db.scalars(stmt.order_by(Ciudad.codigo)))


def crear_ciudad(db: Session, data: s.CiudadCreate) -> Ciudad:
    _codigo_unico(db, Ciudad, data.codigo, "una ciudad")
    ciudad = Ciudad(**data.model_dump())
    db.add(ciudad)
    _commit(db, ciudad)
    return ciudad


def actualizar_ciudad(db: Session, ciudad_id: int, data: s.CiudadUpdate) -> Ciudad:
    ciudad = obtener_ciudad(db, ciudad_id)
    cambios = _cambios(data)
    for campo in ("codigo", "nombre", "activo"):
        if campo in cambios and cambios[campo] is None:
            cambios.pop(campo)
    if cambios.get("codigo") and cambios["codigo"] != ciudad.codigo:
        _codigo_unico(db, Ciudad, cambios["codigo"], "una ciudad", excluir_id=ciudad.id)
    _aplicar_auditado(db, ciudad, cambios, "ciudad")
    _commit(db, ciudad)
    return ciudad


# =========================================================================================
# Insumos
# =========================================================================================
def obtener_insumo(db: Session, insumo_id: int) -> Insumo:
    return _get(db, Insumo, insumo_id, "Insumo")


def listar_insumos(
    db: Session,
    *,
    q: str | None = None,
    tipo: TipoInsumo | None = None,
    activo: bool | None = None,
    unidad_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Insumo], int]:
    stmt = select(Insumo)
    if q:
        stmt = stmt.where(or_(contiene(Insumo.codigo, q), contiene(Insumo.descripcion, q)))
    if tipo is not None:
        stmt = stmt.where(Insumo.tipo == tipo)
    if activo is not None:
        stmt = stmt.where(Insumo.activo.is_(activo))
    if unidad_id is not None:
        stmt = stmt.where(Insumo.unidad_id == unidad_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(Insumo.codigo).limit(limit).offset(offset)).unique().all()
    return list(items), int(total)


def insumo_en_uso(db: Session, insumo_id: int) -> bool:
    """True si el insumo aparece en algún APU, snapshot de presupuesto o compromiso."""
    for stmt in (
        select(ApuInsumo.id).where(ApuInsumo.insumo_id == insumo_id).limit(1),
        select(PresupuestoLineaInsumo.id).where(PresupuestoLineaInsumo.insumo_id == insumo_id).limit(1),
        select(CompromisoLinea.id).where(CompromisoLinea.insumo_id == insumo_id).limit(1),
    ):
        if db.scalar(stmt) is not None:
            return True
    return False


def insumo_en_version_no_editable(db: Session, insumo_id: int) -> bool:
    """True si el insumo está en el snapshot de alguna versión APROBADA o CERRADA."""
    stmt = (
        select(PresupuestoLineaInsumo.id)
        .join(PresupuestoLinea, PresupuestoLinea.id == PresupuestoLineaInsumo.linea_id)
        .join(PresupuestoVersion, PresupuestoVersion.id == PresupuestoLinea.version_id)
        .where(
            PresupuestoLineaInsumo.insumo_id == insumo_id,
            PresupuestoVersion.estado != EstadoVersion.BORRADOR,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def crear_insumo(db: Session, data: s.InsumoCreate) -> Insumo:
    _codigo_unico(db, Insumo, data.codigo, "un insumo")
    _ref_activa(db, Unidad, data.unidad_id, "La unidad")
    insumo = Insumo(**data.model_dump())
    db.add(insumo)
    _commit(db, insumo)
    return insumo


def actualizar_insumo(db: Session, insumo_id: int, data: s.InsumoUpdate) -> Insumo:
    insumo = obtener_insumo(db, insumo_id)
    cambios = _cambios(data)
    for campo in ("codigo", "descripcion", "unidad_id", "tipo", "activo"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"El campo '{campo}' no puede quedar vacío", details={"campo": campo})
    if "codigo" in cambios and cambios["codigo"] != insumo.codigo:
        if insumo_en_uso(db, insumo.id):
            raise BusinessRuleError(
                f"No se puede cambiar el código del insumo '{insumo.codigo}': está usado en APU, "
                "presupuestos o compromisos",
                details={"insumo_id": insumo.id},
            )
        _codigo_unico(db, Insumo, cambios["codigo"], "un insumo", excluir_id=insumo.id)
    if "unidad_id" in cambios and cambios["unidad_id"] != insumo.unidad_id:
        if insumo_en_uso(db, insumo.id):
            raise BusinessRuleError(
                f"No se puede cambiar la unidad del insumo '{insumo.codigo}': está usado en APU, "
                "presupuestos o compromisos (sus cantidades quedarían en otra unidad)",
                details={"insumo_id": insumo.id},
            )
        _ref_activa(db, Unidad, cambios["unidad_id"], "La unidad")
    if "tipo" in cambios and cambios["tipo"] != insumo.tipo and insumo_en_version_no_editable(db, insumo.id):
        raise BusinessRuleError(
            f"No se puede cambiar el tipo del insumo '{insumo.codigo}': está en versiones de "
            "presupuesto APROBADAS o CERRADAS (su explosión por tipo es inmutable)",
            details={"insumo_id": insumo.id},
        )
    _aplicar_auditado(db, insumo, cambios, "insumo")
    _commit(db, insumo)
    return insumo


def historico_precios_insumo(
    db: Session, insumo_id: int, *, ciudad_id: int | None = None
) -> list[s.PrecioHistoricoOut]:
    obtener_insumo(db, insumo_id)
    stmt = (
        select(PrecioInsumo, ListaPrecios, Ciudad)
        .join(ListaPrecios, ListaPrecios.id == PrecioInsumo.lista_id)
        .join(Ciudad, Ciudad.id == ListaPrecios.ciudad_id)
        .where(PrecioInsumo.insumo_id == insumo_id)
    )
    if ciudad_id is not None:
        stmt = stmt.where(ListaPrecios.ciudad_id == ciudad_id)
    stmt = stmt.order_by(Ciudad.codigo, ListaPrecios.fecha_desde.desc())
    return [
        s.PrecioHistoricoOut(
            lista_id=lista.id,
            lista_codigo=lista.codigo,
            lista_nombre=lista.nombre,
            ciudad_id=ciudad.id,
            ciudad_codigo=ciudad.codigo,
            fecha_desde=lista.fecha_desde,
            precio=precio.precio,
        )
        for precio, lista, ciudad in db.execute(stmt).unique()
    ]


# =========================================================================================
# Listas de precios
# =========================================================================================
def obtener_lista(db: Session, lista_id: int) -> ListaPrecios:
    return _get(db, ListaPrecios, lista_id, "Lista de precios")


def contar_precios(db: Session, lista_ids: Iterable[int]) -> dict[int, int]:
    ids = list(lista_ids)
    if not ids:
        return {}
    stmt = (
        select(PrecioInsumo.lista_id, func.count(PrecioInsumo.id))
        .where(PrecioInsumo.lista_id.in_(ids))
        .group_by(PrecioInsumo.lista_id)
    )
    conteo = {lid: int(n) for lid, n in db.execute(stmt)}
    return {lid: conteo.get(lid, 0) for lid in ids}


def lista_out(db: Session, lista: ListaPrecios) -> s.ListaPreciosOut:
    return s.ListaPreciosOut.desde(lista, contar_precios(db, [lista.id])[lista.id])


def listar_listas(
    db: Session, *, ciudad_id: int | None = None, activo: bool | None = None
) -> list[s.ListaPreciosOut]:
    stmt = select(ListaPrecios).join(Ciudad, Ciudad.id == ListaPrecios.ciudad_id)
    if ciudad_id is not None:
        stmt = stmt.where(ListaPrecios.ciudad_id == ciudad_id)
    if activo is not None:
        stmt = stmt.where(ListaPrecios.activo.is_(activo))
    listas = list(db.scalars(stmt.order_by(Ciudad.codigo, ListaPrecios.fecha_desde.desc())).unique())
    conteo = contar_precios(db, [lista.id for lista in listas])
    return [s.ListaPreciosOut.desde(lista, conteo[lista.id]) for lista in listas]


def crear_lista(db: Session, data: s.ListaPreciosCreate) -> ListaPrecios:
    _codigo_unico(db, ListaPrecios, data.codigo, "una lista de precios")
    ciudad = _ref_activa(db, Ciudad, data.ciudad_id, "La ciudad")
    existe = db.scalar(
        select(ListaPrecios.id).where(
            ListaPrecios.ciudad_id == data.ciudad_id, ListaPrecios.fecha_desde == data.fecha_desde
        )
    )
    if existe is not None:
        raise ConflictError(
            f"Ya existe una lista de precios para {ciudad.codigo} vigente desde {data.fecha_desde.isoformat()}",
            details={"lista_id": existe},
        )
    origen: ListaPrecios | None = None
    if data.copiar_de_lista_id is not None:
        origen = db.get(ListaPrecios, data.copiar_de_lista_id)
        if origen is None:
            raise BusinessRuleError(
                f"La lista origen con id {data.copiar_de_lista_id} no existe",
                details={"copiar_de_lista_id": data.copiar_de_lista_id},
            )
    lista = ListaPrecios(**data.model_dump(exclude={"copiar_de_lista_id"}))
    db.add(lista)
    db.flush()
    copiados = 0
    if origen is not None:
        for p in db.scalars(select(PrecioInsumo).where(PrecioInsumo.lista_id == origen.id)):
            db.add(PrecioInsumo(lista_id=lista.id, insumo_id=p.insumo_id, precio=p.precio, fuente=p.fuente))
            copiados += 1
    registrar_auditoria(
        db,
        accion=Accion.CREAR,
        entidad="lista_precios",
        entidad_id=lista.id,
        detalle={
            "codigo": lista.codigo,
            "ciudad": ciudad.codigo,
            "fecha_desde": lista.fecha_desde,
            "copiada_de": origen.id if origen else None,
            "precios_copiados": copiados,
        },
    )
    _commit(db, lista)
    return lista


def actualizar_lista(db: Session, lista_id: int, data: s.ListaPreciosUpdate) -> ListaPrecios:
    lista = obtener_lista(db, lista_id)
    cambios = _cambios(data)
    for campo in ("nombre", "activo"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"El campo '{campo}' no puede quedar vacío", details={"campo": campo})
    if "activo" in cambios and cambios["activo"] != lista.activo:
        registrar_auditoria(
            db,
            accion=Accion.ACTUALIZAR,
            entidad="lista_precios",
            entidad_id=lista.id,
            detalle={"activo": cambios["activo"]},
        )
    _aplicar(lista, cambios)
    _commit(db, lista)
    return lista


def listar_precios_lista(
    db: Session,
    lista_id: int,
    *,
    q: str | None = None,
    tipo: TipoInsumo | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[s.PrecioOut], int]:
    obtener_lista(db, lista_id)
    stmt = (
        select(PrecioInsumo, Insumo)
        .join(Insumo, Insumo.id == PrecioInsumo.insumo_id)
        .where(PrecioInsumo.lista_id == lista_id)
    )
    if q:
        stmt = stmt.where(or_(contiene(Insumo.codigo, q), contiene(Insumo.descripcion, q)))
    if tipo is not None:
        stmt = stmt.where(Insumo.tipo == tipo)
    total = (
        db.scalar(select(func.count()).select_from(stmt.with_only_columns(PrecioInsumo.id).subquery())) or 0
    )
    filas = db.execute(stmt.order_by(Insumo.codigo).limit(limit).offset(offset)).unique().all()
    return [s.PrecioOut.desde(p, i) for p, i in filas], int(total)


def cargar_precios(db: Session, lista_id: int, data: s.PreciosLote) -> s.PreciosLoteResultado:
    """Upsert de precios por ``insumo_id`` (todo o nada)."""
    lista = obtener_lista(db, lista_id)
    ids = [p.insumo_id for p in data.precios]
    existentes_insumo = set(db.scalars(select(Insumo.id).where(Insumo.id.in_(ids))))
    faltantes = sorted(set(ids) - existentes_insumo)
    if faltantes:
        raise BusinessRuleError(
            f"Hay insumos que no existen: {faltantes}", details={"insumos_inexistentes": faltantes}
        )
    actuales = {
        p.insumo_id: p
        for p in db.scalars(
            select(PrecioInsumo).where(PrecioInsumo.lista_id == lista.id, PrecioInsumo.insumo_id.in_(ids))
        )
    }
    creados = actualizados = 0
    for p in data.precios:
        actual = actuales.get(p.insumo_id)
        if actual is None:
            db.add(PrecioInsumo(lista_id=lista.id, insumo_id=p.insumo_id, precio=p.precio, fuente=p.fuente))
            creados += 1
        else:
            actual.precio = p.precio
            if "fuente" in p.model_fields_set:
                actual.fuente = p.fuente
            actualizados += 1
    registrar_auditoria(
        db,
        accion=Accion.ACTUALIZAR,
        entidad="lista_precios",
        entidad_id=lista.id,
        detalle={"operacion": "cargar_precios", "creados": creados, "actualizados": actualizados},
    )
    db.commit()
    return s.PreciosLoteResultado(creados=creados, actualizados=actualizados)


def eliminar_precio(db: Session, lista_id: int, insumo_id: int) -> None:
    lista = obtener_lista(db, lista_id)
    precio = db.scalar(
        select(PrecioInsumo).where(PrecioInsumo.lista_id == lista.id, PrecioInsumo.insumo_id == insumo_id)
    )
    if precio is None:
        raise NotFoundError(
            f"El insumo {insumo_id} no tiene precio en la lista '{lista.codigo}'",
            details={"lista_id": lista_id, "insumo_id": insumo_id},
        )
    registrar_auditoria(
        db,
        accion=Accion.ELIMINAR,
        entidad="precio_insumo",
        entidad_id=precio.id,
        detalle={"lista_id": lista.id, "insumo_id": insumo_id, "precio": precio.precio},
    )
    db.delete(precio)
    db.commit()


# --- Precio vigente (API reutilizable) ---------------------------------------------------
def precio_vigente(db: Session, insumo_id: int, fecha: date, ciudad_id: int) -> PrecioVigente | None:
    """Precio vigente de un insumo en una ciudad a una fecha.

    Regla: precio del insumo en la lista ACTIVA de la ciudad con mayor ``fecha_desde <= fecha``
    que lo contenga. Devuelve ``None`` si no hay precio. Delegado en
    ``app.modules.adpro.valorizacion.precio_vigente`` (fuente única de la regla).
    """
    return valorizacion.precio_vigente(db, insumo_id, ciudad_id, fecha)


def precios_vigentes(
    db: Session, ciudad_id: int, fecha: date, insumo_ids: Iterable[int]
) -> list[PrecioVigente]:
    """Precios vigentes de varios insumos (los que no tienen precio no aparecen), orden por insumo."""
    obtener_ciudad(db, ciudad_id)
    res = valorizacion.precios_vigentes(db, insumo_ids, ciudad_id, fecha)
    return [res[k] for k in sorted(res)]


# =========================================================================================
# Proyectos, etapas y torres
# =========================================================================================
def obtener_proyecto(db: Session, proyecto_id: int) -> Proyecto:
    return _get(db, Proyecto, proyecto_id, "Proyecto")


def listar_proyectos(
    db: Session,
    *,
    q: str | None = None,
    estado: Any = None,
    tipo: Any = None,
    ciudad_id: int | None = None,
) -> list[Proyecto]:
    stmt = select(Proyecto)
    if q:
        stmt = stmt.where(or_(contiene(Proyecto.codigo, q), contiene(Proyecto.nombre, q)))
    if estado is not None:
        stmt = stmt.where(Proyecto.estado == estado)
    if tipo is not None:
        stmt = stmt.where(Proyecto.tipo == tipo)
    if ciudad_id is not None:
        stmt = stmt.where(Proyecto.ciudad_id == ciudad_id)
    return list(db.scalars(stmt.order_by(Proyecto.codigo)).unique())


def crear_proyecto(db: Session, data: s.ProyectoCreate) -> Proyecto:
    _codigo_unico(db, Proyecto, data.codigo, "un proyecto")
    _ref_activa(db, Ciudad, data.ciudad_id, "La ciudad")
    proyecto = Proyecto(**data.model_dump())
    db.add(proyecto)
    db.flush()
    registrar_auditoria(
        db,
        accion=Accion.CREAR,
        entidad="proyecto",
        entidad_id=proyecto.id,
        detalle={"codigo": proyecto.codigo},
    )
    _commit(db, proyecto)
    return proyecto


def actualizar_proyecto(db: Session, proyecto_id: int, data: s.ProyectoUpdate) -> Proyecto:
    proyecto = obtener_proyecto(db, proyecto_id)
    cambios = _cambios(data)
    for campo in ("nombre", "ciudad_id", "tipo", "estado"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"El campo '{campo}' no puede quedar vacío", details={"campo": campo})
    if "ciudad_id" in cambios and cambios["ciudad_id"] != proyecto.ciudad_id:
        _ref_activa(db, Ciudad, cambios["ciudad_id"], "La ciudad")
    inicio = cambios.get("fecha_inicio", proyecto.fecha_inicio)
    fin = cambios.get("fecha_fin_estimada", proyecto.fecha_fin_estimada)
    if inicio and fin and fin < inicio:
        raise BusinessRuleError("fecha_fin_estimada no puede ser anterior a fecha_inicio")
    if "estado" in cambios and cambios["estado"] != proyecto.estado:
        registrar_auditoria(
            db,
            accion=Accion.ACTUALIZAR,
            entidad="proyecto",
            entidad_id=proyecto.id,
            detalle={"estado_anterior": proyecto.estado, "estado_nuevo": cambios["estado"]},
        )
    _aplicar(proyecto, cambios)
    db.commit()
    db.expire(proyecto)
    db.refresh(proyecto)
    return proyecto


def obtener_etapa(db: Session, etapa_id: int) -> Etapa:
    return _get(db, Etapa, etapa_id, "Etapa")


def _etapa_codigo_unico(db: Session, proyecto_id: int, codigo: str, excluir_id: int | None = None) -> None:
    stmt = select(Etapa.id).where(Etapa.proyecto_id == proyecto_id, Etapa.codigo == codigo)
    if excluir_id is not None:
        stmt = stmt.where(Etapa.id != excluir_id)
    if db.scalar(stmt) is not None:
        raise ConflictError(
            f"El proyecto ya tiene una etapa con código '{codigo}'", details={"codigo": codigo}
        )


def crear_etapa(db: Session, proyecto_id: int, data: s.EtapaCreate) -> Etapa:
    proyecto = obtener_proyecto(db, proyecto_id)
    _etapa_codigo_unico(db, proyecto.id, data.codigo)
    etapa = Etapa(proyecto_id=proyecto.id, **data.model_dump())
    db.add(etapa)
    _commit(db, etapa)
    return etapa


def actualizar_etapa(db: Session, etapa_id: int, data: s.EtapaUpdate) -> Etapa:
    etapa = obtener_etapa(db, etapa_id)
    cambios = _cambios(data)
    for campo in ("codigo", "nombre", "orden"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"El campo '{campo}' no puede quedar vacío", details={"campo": campo})
    if "codigo" in cambios and cambios["codigo"] != etapa.codigo:
        _etapa_codigo_unico(db, etapa.proyecto_id, cambios["codigo"], excluir_id=etapa.id)
    _aplicar_auditado(db, etapa, cambios, "etapa")
    _commit(db, etapa)
    return etapa


def eliminar_etapa(db: Session, etapa_id: int) -> None:
    etapa = obtener_etapa(db, etapa_id)
    n = db.scalar(select(func.count(Presupuesto.id)).where(Presupuesto.etapa_id == etapa.id)) or 0
    if n:
        raise ConflictError(
            f"La etapa '{etapa.codigo}' tiene {n} presupuesto(s) asociados y no se puede eliminar",
            details={"presupuestos": int(n)},
        )
    registrar_auditoria(
        db,
        accion=Accion.ELIMINAR,
        entidad="etapa",
        entidad_id=etapa.id,
        detalle={"proyecto_id": etapa.proyecto_id, "codigo": etapa.codigo},
    )
    db.delete(etapa)
    db.commit()


def obtener_torre(db: Session, torre_id: int) -> Torre:
    return _get(db, Torre, torre_id, "Torre")


def _torre_codigo_unico(db: Session, etapa_id: int, codigo: str, excluir_id: int | None = None) -> None:
    stmt = select(Torre.id).where(Torre.etapa_id == etapa_id, Torre.codigo == codigo)
    if excluir_id is not None:
        stmt = stmt.where(Torre.id != excluir_id)
    if db.scalar(stmt) is not None:
        raise ConflictError(f"La etapa ya tiene una torre con código '{codigo}'", details={"codigo": codigo})


def crear_torre(db: Session, etapa_id: int, data: s.TorreCreate) -> Torre:
    etapa = obtener_etapa(db, etapa_id)
    _torre_codigo_unico(db, etapa.id, data.codigo)
    torre = Torre(etapa_id=etapa.id, **data.model_dump())
    db.add(torre)
    _commit(db, torre)
    return torre


def actualizar_torre(db: Session, torre_id: int, data: s.TorreUpdate) -> Torre:
    torre = obtener_torre(db, torre_id)
    cambios = _cambios(data)
    for campo in ("codigo", "nombre"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"El campo '{campo}' no puede quedar vacío", details={"campo": campo})
    if "codigo" in cambios and cambios["codigo"] != torre.codigo:
        _torre_codigo_unico(db, torre.etapa_id, cambios["codigo"], excluir_id=torre.id)
    _aplicar_auditado(db, torre, cambios, "torre")
    _commit(db, torre)
    return torre


def eliminar_torre(db: Session, torre_id: int) -> None:
    torre = obtener_torre(db, torre_id)
    registrar_auditoria(
        db,
        accion=Accion.ELIMINAR,
        entidad="torre",
        entidad_id=torre.id,
        detalle={"etapa_id": torre.etapa_id, "codigo": torre.codigo},
    )
    db.delete(torre)
    db.commit()


# =========================================================================================
# EDT presupuestal
# =========================================================================================
def obtener_edt_nodo(db: Session, nodo_id: int) -> EdtNodo:
    return _get(db, EdtNodo, nodo_id, "Nodo EDT")


def obtener_item_edt(db: Session, item_id: int) -> EdtNodo:
    """Nodo EDT que debe ser de nivel ITEM (404 si no existe, 422 si es otro nivel)."""
    nodo = obtener_edt_nodo(db, item_id)
    if nodo.nivel != NivelEdt.ITEM:
        raise BusinessRuleError(
            f"El nodo EDT '{nodo.codigo}' es de nivel {nodo.nivel.value}, se esperaba ITEM",
            details={"id": nodo.id, "nivel": nodo.nivel.value},
        )
    return nodo


def items_con_apu(db: Session, nodo_ids: Iterable[int]) -> set[int]:
    ids = list(nodo_ids)
    if not ids:
        return set()
    return set(db.scalars(select(Apu.item_id).where(Apu.item_id.in_(ids))))


def edt_out(db: Session, nodo: EdtNodo) -> s.EdtNodoOut:
    return s.EdtNodoOut.desde(nodo, nodo.id in items_con_apu(db, [nodo.id]))


def listar_edt(
    db: Session,
    *,
    nivel: NivelEdt | None = None,
    parent_id: int | None = None,
    q: str | None = None,
    activo: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[s.EdtNodoOut], int]:
    stmt = select(EdtNodo)
    if nivel is not None:
        stmt = stmt.where(EdtNodo.nivel == nivel)
    if parent_id is not None:
        stmt = stmt.where(EdtNodo.parent_id == parent_id)
    if q:
        stmt = stmt.where(or_(contiene(EdtNodo.codigo, q), contiene(EdtNodo.descripcion, q)))
    if activo is not None:
        stmt = stmt.where(EdtNodo.activo.is_(activo))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    nodos = list(db.scalars(stmt.order_by(EdtNodo.codigo).limit(limit).offset(offset)).unique())
    con_apu = items_con_apu(db, [n.id for n in nodos])
    return [s.EdtNodoOut.desde(n, n.id in con_apu) for n in nodos], int(total)


def arbol_edt(
    db: Session,
    *,
    capitulo_id: int | None = None,
    hasta_nivel: NivelEdt = NivelEdt.ITEM,
    activo: bool | None = None,
) -> list[s.EdtArbolNodo]:
    """Árbol de la EDT (raíces = capítulos), ordenado por ``orden`` y ``codigo``.

    Con ``activo=True`` se excluyen los nodos inactivos y todo su subárbol.
    """
    if capitulo_id is not None:
        cap = obtener_edt_nodo(db, capitulo_id)
        if cap.nivel != NivelEdt.CAPITULO:
            raise BusinessRuleError(f"El nodo '{cap.codigo}' no es un CAPITULO", details={"id": cap.id})
    niveles = [n for n in NivelEdt if n.profundidad <= hasta_nivel.profundidad]
    stmt = select(EdtNodo).where(EdtNodo.nivel.in_(niveles))
    if activo is not None:
        stmt = stmt.where(EdtNodo.activo.is_(activo))
    nodos = list(db.scalars(stmt.order_by(EdtNodo.orden, EdtNodo.codigo)).unique())
    con_apu = items_con_apu(db, [n.id for n in nodos if n.nivel == NivelEdt.ITEM])

    hijos: dict[int | None, list[EdtNodo]] = {}
    for n in nodos:
        hijos.setdefault(n.parent_id, []).append(n)

    def construir(n: EdtNodo) -> s.EdtArbolNodo:
        return s.EdtArbolNodo(
            **s.EdtNodoOut._campos(n, n.id in con_apu),
            hijos=[construir(h) for h in hijos.get(n.id, [])],
        )

    raices = [n for n in hijos.get(None, []) if capitulo_id is None or n.id == capitulo_id]
    return [construir(r) for r in raices]


def detalle_edt(db: Session, nodo_id: int) -> s.EdtNodoDetalleOut:
    nodo = obtener_edt_nodo(db, nodo_id)
    ruta: list[s.EdtRutaNodo] = []
    actual: EdtNodo | None = nodo
    while actual is not None:
        ruta.append(
            s.EdtRutaNodo(
                id=actual.id, nivel=actual.nivel, codigo=actual.codigo, descripcion=actual.descripcion
            )
        )
        actual = actual.parent
    ruta.reverse()
    con_apu = nodo.id in items_con_apu(db, [nodo.id])
    return s.EdtNodoDetalleOut(**s.EdtNodoOut._campos(nodo, con_apu), ruta=ruta)


def _validar_unidad_nivel(db: Session, nivel: NivelEdt, unidad_id: int | None) -> None:
    if nivel == NivelEdt.ITEM:
        if unidad_id is None:
            raise BusinessRuleError("Los ítems de la EDT requieren unidad de medida (unidad_id)")
        _ref_activa(db, Unidad, unidad_id, "La unidad")
    elif unidad_id is not None:
        raise BusinessRuleError(
            f"Solo los nodos de nivel ITEM llevan unidad; un {nivel.value} no debe tener unidad_id"
        )


def crear_edt_nodo(db: Session, data: s.EdtNodoCreate) -> EdtNodo:
    nivel = data.nivel
    padre_requerido = nivel.padre_requerido
    padre: EdtNodo | None = None
    if padre_requerido is None:
        if data.parent_id is not None:
            raise BusinessRuleError("Un CAPITULO es raíz de la EDT y no puede tener padre (parent_id)")
        if "." in data.codigo:
            raise BusinessRuleError(
                f"El código de un CAPITULO no lleva punto (recibido '{data.codigo}', ejemplo '01')"
            )
    else:
        if data.parent_id is None:
            raise BusinessRuleError(f"Un {nivel.value} requiere un padre de nivel {padre_requerido.value}")
        padre = db.get(EdtNodo, data.parent_id)
        if padre is None:
            raise BusinessRuleError(
                f"El nodo padre con id {data.parent_id} no existe", details={"parent_id": data.parent_id}
            )
        if padre.nivel != padre_requerido:
            raise BusinessRuleError(
                f"Un {nivel.value} debe colgar de un {padre_requerido.value}; el padre '{padre.codigo}' "
                f"es {padre.nivel.value}",
                details={"parent_id": padre.id, "nivel_padre": padre.nivel.value},
            )
        if not padre.activo:
            raise BusinessRuleError(f"El nodo padre '{padre.codigo}' está inactivo")
        prefijo = f"{padre.codigo}."
        sufijo = data.codigo[len(prefijo) :]
        if not data.codigo.startswith(prefijo) or not sufijo or "." in sufijo:
            raise BusinessRuleError(
                f"El código '{data.codigo}' debe ser el código del padre seguido de un segmento "
                f"(p. ej. '{prefijo}01')",
                details={"codigo_padre": padre.codigo},
            )
    _validar_unidad_nivel(db, nivel, data.unidad_id)
    _codigo_unico(db, EdtNodo, data.codigo, "un nodo EDT")
    valores = data.model_dump()
    if valores.get("orden") is None:
        valores["orden"] = 0
    nodo = EdtNodo(**valores)
    db.add(nodo)
    _commit(db, nodo)
    return nodo


def actualizar_edt_nodo(db: Session, nodo_id: int, data: s.EdtNodoUpdate) -> EdtNodo:
    nodo = obtener_edt_nodo(db, nodo_id)
    cambios = _cambios(data)
    for campo in ("descripcion", "orden", "activo"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"El campo '{campo}' no puede quedar vacío", details={"campo": campo})
    if "unidad_id" in cambios:
        if cambios["unidad_id"] != nodo.unidad_id or cambios["unidad_id"] is None:
            _validar_unidad_nivel(db, nodo.nivel, cambios["unidad_id"])
    if cambios.get("activo") is True and nodo.parent is not None and not nodo.parent.activo:
        raise BusinessRuleError(f"No se puede activar: el nodo padre '{nodo.parent.codigo}' está inactivo")
    if "activo" in cambios and cambios["activo"] != nodo.activo:
        registrar_auditoria(
            db,
            accion=Accion.ACTUALIZAR,
            entidad="edt_nodo",
            entidad_id=nodo.id,
            detalle={"codigo": nodo.codigo, "activo": cambios["activo"]},
        )
    _aplicar(nodo, cambios)
    _commit(db, nodo)
    return nodo
