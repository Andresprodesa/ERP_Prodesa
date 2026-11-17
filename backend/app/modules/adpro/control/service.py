"""Lógica de negocio de ADPRO / control (contrato §5).

Funciones puras respecto a HTTP: reciben ``db: Session`` y datos validados, devuelven schemas
o modelos y lanzan ``app.core.errors`` (NotFoundError, ConflictError, BusinessRuleError).
Hacen ``db.commit()`` al final de cada escritura y registran auditoría en operaciones relevantes.
Fórmulas: SIEMPRE ``app.modules.adpro.calculos``; valorización APU vía ``valorizacion``.

Integración con presupuesto: se usa el contrato interno de ``presupuesto.service`` (§6) para
obtener/validar versiones (``obtener_version``, ``asegurar_editable``), la explosión de insumos
(``calcular_explosion``), el resumen con AIU (``calcular_resumen``) y la escritura de líneas en la
importación (``aplicar_lineas``). Así las cifras de control y de presupuesto salen del mismo código.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import Accion, registrar_auditoria
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.query import contiene
from app.core.schemas import Page
from app.modules.adpro.calculos import (
    ZERO,
    asegurar_rango,
    es_periodo_valido,
    participacion_pct,
    q4,
    valor_total_linea,
    variacion_pct,
)
from app.modules.adpro.control import excel as xl
from app.modules.adpro.control.schemas import (
    ComparativoFila,
    ComparativoOut,
    ComparativoTotales,
    CompromisoCreate,
    CompromisoDetalleOut,
    CompromisoLineaIn,
    CompromisoLineaOut,
    CompromisoOut,
    CompromisoUpdate,
    EjecucionLote,
    EjecucionLoteResultado,
    EjecucionOut,
    ImportErrorFila,
    ImportResultado,
    NivelComparativo,
    SerieMensualPunto,
    TableroFila,
    TableroOut,
    VersionRef,
)
from app.modules.adpro.enums import (
    EstadoCompromiso,
    EstadoVersion,
    NivelEdt,
    OrigenValor,
    TipoCompromiso,
    TipoInsumo,
    TipoVersion,
)
from app.modules.adpro.models import (
    Apu,
    Compromiso,
    CompromisoLinea,
    EdtNodo,
    Ejecucion,
    Insumo,
    Presupuesto,
    PresupuestoLinea,
    PresupuestoLineaInsumo,
    PresupuestoVersion,
)
from app.modules.adpro.presupuesto import service as presupuesto_service
from app.modules.adpro.presupuesto.schemas import ExplosionFila, LineaCreate

MAX_BYTES_IMPORTACION = 10 * 1024 * 1024  # 10 MB
NIVELES_COMPARATIVO: tuple[str, ...] = ("item", "insumo", "capitulo")


# =====================================================================================
# Utilidades comunes
# =====================================================================================
def _pesos_txt(v: Decimal) -> str:
    """Formato de pesos para mensajes: 1.250.000."""
    return f"${int(v.to_integral_value()):,}".replace(",", ".")


def _obtener_presupuesto(db: Session, presupuesto_id: int) -> Presupuesto:
    p = db.get(Presupuesto, presupuesto_id)
    if p is None:
        raise NotFoundError(f"Presupuesto {presupuesto_id} no existe")
    return p


def _obtener_version(db: Session, version_id: int) -> PresupuestoVersion:
    return presupuesto_service.obtener_version(db, version_id)


def _version_ref(v: PresupuestoVersion) -> VersionRef:
    return VersionRef.model_validate(v)


def version_control_vigente(db: Session, presupuesto_id: int) -> PresupuestoVersion | None:
    """Última versión CONTROL APROBADA; si no hay, la última APROBADA de cualquier tipo."""
    base = select(PresupuestoVersion).where(
        PresupuestoVersion.presupuesto_id == presupuesto_id,
        PresupuestoVersion.estado == EstadoVersion.APROBADO,
    )
    v = db.scalars(
        base.where(PresupuestoVersion.tipo == TipoVersion.CONTROL).order_by(PresupuestoVersion.numero.desc())
    ).first()
    if v is None:
        v = db.scalars(base.order_by(PresupuestoVersion.numero.desc())).first()
    return v


def _nodos_y_capitulos(
    db: Session, item_ids: Iterable[int]
) -> tuple[dict[int, EdtNodo], dict[int, EdtNodo | None]]:
    """Carga los nodos EDT dados y sus ancestros. Devuelve (nodos por id, capítulo por ítem)."""
    ids = set(item_ids)
    nodos: dict[int, EdtNodo] = {}
    pendientes = set(ids)
    while pendientes:
        filas = db.scalars(select(EdtNodo).where(EdtNodo.id.in_(pendientes))).all()
        for n in filas:
            nodos[n.id] = n
        pendientes = {n.parent_id for n in filas if n.parent_id is not None and n.parent_id not in nodos}
    capitulos: dict[int, EdtNodo | None] = {}
    for iid in ids:
        n = nodos.get(iid)
        saltos = 0
        while n is not None and n.parent_id is not None and saltos < 10:
            n = nodos.get(n.parent_id)
            saltos += 1
        capitulos[iid] = n if n is not None and n.nivel is NivelEdt.CAPITULO else None
    return nodos, capitulos


def _lineas_version(db: Session, version_id: int) -> list[PresupuestoLinea]:
    return list(db.scalars(select(PresupuestoLinea).where(PresupuestoLinea.version_id == version_id)).all())


# =====================================================================================
# 5.1 Comparativo
# =====================================================================================
_Valores = tuple[Decimal | None, Decimal | None, Decimal]  # (cantidad, unitario, total)


def _fila_comparativo(
    *,
    clave_id: int,
    codigo: str,
    descripcion: str,
    unidad_codigo: str | None,
    tipo: TipoInsumo | None,
    capitulo_codigo: str | None,
    base: _Valores | None,
    comp: _Valores | None,
    con_cantidades: bool,
) -> ComparativoFila:
    cero: _Valores = (ZERO, ZERO, ZERO) if con_cantidades else (None, None, ZERO)
    b = base or cero
    c = comp or cero
    if base is None:
        estado = "NUEVO"
    elif comp is None:
        estado = "ELIMINADO"
    elif b == c:
        estado = "IGUAL"
    else:
        estado = "MODIFICADO"
    dif_cant = c[0] - b[0] if con_cantidades and b[0] is not None and c[0] is not None else None
    dif_unit = c[1] - b[1] if con_cantidades and b[1] is not None and c[1] is not None else None
    return ComparativoFila(
        clave_id=clave_id,
        codigo=codigo,
        descripcion=descripcion,
        unidad_codigo=unidad_codigo,
        tipo=tipo,
        capitulo_codigo=capitulo_codigo,
        cantidad_base=b[0],
        cantidad_comparada=c[0],
        unitario_base=b[1],
        unitario_comparado=c[1],
        total_base=b[2],
        total_comparado=c[2],
        diferencia_cantidad=dif_cant,
        diferencia_unitaria=dif_unit,
        impacto=c[2] - b[2],
        variacion_pct=variacion_pct(b[2], c[2]),
        estado=estado,  # type: ignore[arg-type]
    )


def _comparar_items(db: Session, vb: PresupuestoVersion, vc: PresupuestoVersion) -> list[ComparativoFila]:
    lb = {ln.item_id: ln for ln in _lineas_version(db, vb.id)}
    lc = {ln.item_id: ln for ln in _lineas_version(db, vc.id)}
    nodos, caps = _nodos_y_capitulos(db, set(lb) | set(lc))
    filas: list[ComparativoFila] = []
    for iid in set(lb) | set(lc):
        item = nodos[iid]
        cap = caps.get(iid)
        b, c = lb.get(iid), lc.get(iid)
        filas.append(
            _fila_comparativo(
                clave_id=iid,
                codigo=item.codigo,
                descripcion=item.descripcion,
                unidad_codigo=item.unidad.codigo if item.unidad else None,
                tipo=None,
                capitulo_codigo=cap.codigo if cap else None,
                base=(b.cantidad, b.valor_unitario, b.valor_total) if b else None,
                comp=(c.cantidad, c.valor_unitario, c.valor_total) if c else None,
                con_cantidades=True,
            )
        )
    return sorted(filas, key=lambda f: f.codigo)


def _valores_insumo(f: ExplosionFila) -> _Valores:
    return (f.cantidad_total, f.precio_unitario, f.valor_total)


def _explosion_por_insumo(db: Session, version_id: int) -> dict[int, ExplosionFila]:
    """Explosión de insumos desde el snapshot (fuente única: ``presupuesto.calcular_explosion``)."""
    return {f.insumo_id: f for f in presupuesto_service.calcular_explosion(db, version_id).filas}


def _comparar_insumos(db: Session, vb: PresupuestoVersion, vc: PresupuestoVersion) -> list[ComparativoFila]:
    eb = _explosion_por_insumo(db, vb.id)
    ec = _explosion_por_insumo(db, vc.id)
    filas: list[ComparativoFila] = []
    for iid in set(eb) | set(ec):
        ref = eb.get(iid) or ec[iid]
        filas.append(
            _fila_comparativo(
                clave_id=iid,
                codigo=ref.insumo_codigo,
                descripcion=ref.insumo_descripcion,
                unidad_codigo=ref.unidad_codigo,
                tipo=ref.tipo,
                capitulo_codigo=None,
                base=_valores_insumo(eb[iid]) if iid in eb else None,
                comp=_valores_insumo(ec[iid]) if iid in ec else None,
                con_cantidades=True,
            )
        )
    return sorted(filas, key=lambda f: f.codigo)


def _totales_por_capitulo(
    db: Session, version_id: int
) -> dict[int | None, tuple[EdtNodo | None, Decimal, int]]:
    lineas = _lineas_version(db, version_id)
    _, caps = _nodos_y_capitulos(db, {ln.item_id for ln in lineas})
    out: dict[int | None, tuple[EdtNodo | None, Decimal, int]] = {}
    for ln in lineas:
        cap = caps.get(ln.item_id)
        key = cap.id if cap else None
        _, total, n = out.get(key, (cap, ZERO, 0))
        out[key] = (cap, total + ln.valor_total, n + 1)
    return out


def _comparar_capitulos(db: Session, vb: PresupuestoVersion, vc: PresupuestoVersion) -> list[ComparativoFila]:
    tb = _totales_por_capitulo(db, vb.id)
    tc = _totales_por_capitulo(db, vc.id)
    filas: list[ComparativoFila] = []
    for key in set(tb) | set(tc):
        cap = (tb.get(key) or tc[key])[0]
        filas.append(
            _fila_comparativo(
                clave_id=key or 0,
                codigo=cap.codigo if cap else "SIN-CAPITULO",
                descripcion=cap.descripcion if cap else "Ítems sin capítulo",
                unidad_codigo=None,
                tipo=None,
                capitulo_codigo=cap.codigo if cap else None,
                base=(None, None, tb[key][1]) if key in tb else None,
                comp=(None, None, tc[key][1]) if key in tc else None,
                con_cantidades=False,
            )
        )
    return sorted(filas, key=lambda f: f.codigo)


def comparar_versiones(
    db: Session, base_id: int, comparada_id: int, nivel: NivelComparativo
) -> ComparativoOut:
    """Comparativo entre dos versiones (pueden ser de presupuestos distintos, p. ej. FIC vs FIV)."""
    if nivel not in NIVELES_COMPARATIVO:
        raise BusinessRuleError(f"Nivel de comparativo inválido: {nivel}")
    vb = _obtener_version(db, base_id)
    vc = _obtener_version(db, comparada_id)
    if nivel == "item":
        filas = _comparar_items(db, vb, vc)
    elif nivel == "insumo":
        filas = _comparar_insumos(db, vb, vc)
    else:
        filas = _comparar_capitulos(db, vb, vc)
    total_b = sum((f.total_base for f in filas), ZERO)
    total_c = sum((f.total_comparado for f in filas), ZERO)
    return ComparativoOut(
        version_base=_version_ref(vb),
        version_comparada=_version_ref(vc),
        nivel=nivel,
        filas=filas,
        totales=ComparativoTotales(
            total_base=total_b,
            total_comparado=total_c,
            impacto=total_c - total_b,
            variacion_pct=variacion_pct(total_b, total_c),
        ),
    )


# =====================================================================================
# 5.2 Compromisos
# =====================================================================================
def _compromiso_out_campos(c: Compromiso) -> dict[str, Any]:
    return {
        "id": c.id,
        "presupuesto_id": c.presupuesto_id,
        "tipo": c.tipo,
        "numero": c.numero,
        "fecha": c.fecha,
        "tercero": c.tercero,
        "descripcion": c.descripcion,
        "estado": c.estado,
        "valor_total": c.valor_total,
        "num_lineas": len(c.lineas),
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "created_by": c.created_by,
        "updated_by": c.updated_by,
    }


def _advertencias_compromiso(db: Session, c: Compromiso) -> list[str]:
    if c.estado is EstadoCompromiso.ANULADO:
        return []
    version = version_control_vigente(db, c.presupuesto_id)
    if version is None:
        return ["El presupuesto no tiene una versión APROBADA para validar el compromiso"]
    item_ids = {ln.item_id for ln in c.lineas}
    presup = dict(
        db.execute(
            select(PresupuestoLinea.item_id, PresupuestoLinea.valor_total).where(
                PresupuestoLinea.version_id == version.id, PresupuestoLinea.item_id.in_(item_ids)
            )
        ).all()
    )
    comprometido = dict(
        db.execute(
            select(CompromisoLinea.item_id, func.sum(CompromisoLinea.valor_total))
            .join(Compromiso, Compromiso.id == CompromisoLinea.compromiso_id)
            .where(
                Compromiso.presupuesto_id == c.presupuesto_id,
                Compromiso.estado != EstadoCompromiso.ANULADO,
                CompromisoLinea.item_id.in_(item_ids),
            )
            .group_by(CompromisoLinea.item_id)
        ).all()
    )
    nodos, _ = _nodos_y_capitulos(db, item_ids)
    out: list[str] = []
    for iid in sorted(item_ids, key=lambda i: nodos[i].codigo):
        codigo = nodos[iid].codigo
        if iid not in presup:
            out.append(
                f"El ítem {codigo} no está en la versión de control {version.numero} ({version.nombre})"
            )
            continue
        comp = Decimal(comprometido.get(iid) or ZERO)
        if comp > presup[iid]:
            out.append(
                f"Lo comprometido en el ítem {codigo} ({_pesos_txt(comp)}) supera lo presupuestado "
                f"({_pesos_txt(presup[iid])})"
            )
    return out


def _detalle_compromiso(db: Session, c: Compromiso) -> CompromisoDetalleOut:
    lineas = [
        CompromisoLineaOut(
            id=ln.id,
            item_id=ln.item_id,
            item_codigo=ln.item.codigo,
            item_descripcion=ln.item.descripcion,
            insumo_id=ln.insumo_id,
            insumo_codigo=ln.insumo.codigo if ln.insumo else None,
            descripcion=ln.descripcion,
            cantidad=ln.cantidad,
            valor_unitario=ln.valor_unitario,
            valor_total=ln.valor_total,
        )
        for ln in sorted(c.lineas, key=lambda x: (x.item.codigo, x.id or 0))
    ]
    return CompromisoDetalleOut(
        **_compromiso_out_campos(c), lineas=lineas, advertencias=_advertencias_compromiso(db, c)
    )


def _cargar_compromiso(db: Session, compromiso_id: int) -> Compromiso:
    c = db.get(Compromiso, compromiso_id)
    if c is None:
        raise NotFoundError(f"Compromiso {compromiso_id} no existe")
    return c


def _validar_lineas_compromiso(db: Session, lineas: list[CompromisoLineaIn]) -> None:
    item_ids = {ln.item_id for ln in lineas}
    insumo_ids = {ln.insumo_id for ln in lineas if ln.insumo_id is not None}
    items = {n.id: n for n in db.scalars(select(EdtNodo).where(EdtNodo.id.in_(item_ids)))}
    insumos = set(db.scalars(select(Insumo.id).where(Insumo.id.in_(insumo_ids)))) if insumo_ids else set()
    errores: list[dict[str, Any]] = []
    for i, ln in enumerate(lineas):
        nodo = items.get(ln.item_id)
        if nodo is None:
            errores.append({"indice": i, "mensaje": f"El ítem {ln.item_id} no existe"})
        elif nodo.nivel is not NivelEdt.ITEM:
            errores.append({"indice": i, "mensaje": f"El nodo {nodo.codigo} no es de nivel ITEM"})
        if ln.insumo_id is not None and ln.insumo_id not in insumos:
            errores.append({"indice": i, "mensaje": f"El insumo {ln.insumo_id} no existe"})
    if errores:
        raise BusinessRuleError("Hay líneas de compromiso inválidas", details=errores)


def _asignar_lineas(c: Compromiso, lineas: list[CompromisoLineaIn]) -> None:
    c.lineas.clear()
    total = ZERO
    for ln in lineas:
        vt = valor_total_linea(ln.cantidad, ln.valor_unitario)
        total += vt
        c.lineas.append(
            CompromisoLinea(
                item_id=ln.item_id,
                insumo_id=ln.insumo_id,
                descripcion=ln.descripcion,
                cantidad=q4(ln.cantidad),
                valor_unitario=q4(ln.valor_unitario),
                valor_total=vt,
            )
        )
    c.valor_total = asegurar_rango(total, "valor total del compromiso")


def _verificar_numero_unico(
    db: Session, presupuesto_id: int, tipo: TipoCompromiso, numero: str, excluir_id: int | None = None
) -> None:
    stmt = select(Compromiso.id).where(
        Compromiso.presupuesto_id == presupuesto_id, Compromiso.tipo == tipo, Compromiso.numero == numero
    )
    if excluir_id is not None:
        stmt = stmt.where(Compromiso.id != excluir_id)
    if db.scalar(stmt) is not None:
        raise ConflictError(f"Ya existe un compromiso {tipo.value} número {numero} en este presupuesto")


def listar_compromisos(
    db: Session,
    *,
    presupuesto_id: int | None = None,
    estado: EstadoCompromiso | None = None,
    tipo: TipoCompromiso | None = None,
    item_id: int | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[CompromisoOut]:
    stmt = select(Compromiso)
    if presupuesto_id is not None:
        stmt = stmt.where(Compromiso.presupuesto_id == presupuesto_id)
    if estado is not None:
        stmt = stmt.where(Compromiso.estado == estado)
    if tipo is not None:
        stmt = stmt.where(Compromiso.tipo == tipo)
    if item_id is not None:
        stmt = stmt.where(
            Compromiso.id.in_(select(CompromisoLinea.compromiso_id).where(CompromisoLinea.item_id == item_id))
        )
    if q:
        stmt = stmt.where(
            or_(
                contiene(Compromiso.numero, q),
                contiene(Compromiso.tercero, q),
                contiene(Compromiso.descripcion, q),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    filas = db.scalars(
        stmt.options(selectinload(Compromiso.lineas))
        .order_by(Compromiso.fecha.desc(), Compromiso.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[CompromisoOut](
        items=[CompromisoOut(**_compromiso_out_campos(c)) for c in filas],
        total=int(total),
        limit=limit,
        offset=offset,
    )


def obtener_compromiso(db: Session, compromiso_id: int) -> CompromisoDetalleOut:
    return _detalle_compromiso(db, _cargar_compromiso(db, compromiso_id))


def crear_compromiso(db: Session, data: CompromisoCreate) -> CompromisoDetalleOut:
    _obtener_presupuesto(db, data.presupuesto_id)
    _verificar_numero_unico(db, data.presupuesto_id, data.tipo, data.numero)
    _validar_lineas_compromiso(db, data.lineas)
    c = Compromiso(
        presupuesto_id=data.presupuesto_id,
        tipo=data.tipo,
        numero=data.numero,
        fecha=data.fecha,
        tercero=data.tercero,
        descripcion=data.descripcion,
        estado=EstadoCompromiso.VIGENTE,
    )
    _asignar_lineas(c, data.lineas)
    db.add(c)
    db.flush()
    registrar_auditoria(
        db,
        accion=Accion.CREAR,
        entidad="compromiso",
        entidad_id=c.id,
        detalle={"tipo": c.tipo, "numero": c.numero, "valor_total": c.valor_total},
    )
    db.commit()
    return _detalle_compromiso(db, c)


def _asegurar_vigente(c: Compromiso) -> None:
    if c.estado is not EstadoCompromiso.VIGENTE:
        raise BusinessRuleError(
            f"El compromiso está {c.estado.value}; solo los VIGENTES se pueden modificar",
            details={"compromiso_id": c.id, "estado": c.estado.value},
        )


def actualizar_compromiso(db: Session, compromiso_id: int, data: CompromisoUpdate) -> CompromisoDetalleOut:
    c = _cargar_compromiso(db, compromiso_id)
    _asegurar_vigente(c)
    cambios = data.model_dump(exclude_unset=True)
    tipo = data.tipo if "tipo" in cambios and data.tipo else c.tipo
    numero = data.numero.strip() if "numero" in cambios and data.numero else c.numero
    if (tipo, numero) != (c.tipo, c.numero):
        _verificar_numero_unico(db, c.presupuesto_id, tipo, numero, excluir_id=c.id)
    c.tipo, c.numero = tipo, numero
    if "fecha" in cambios and data.fecha is not None:
        c.fecha = data.fecha
    if "tercero" in cambios and data.tercero:
        c.tercero = data.tercero.strip()
    if "descripcion" in cambios:
        c.descripcion = data.descripcion
    if data.lineas is not None:
        _validar_lineas_compromiso(db, data.lineas)
        _asignar_lineas(c, data.lineas)
    db.flush()
    registrar_auditoria(
        db,
        accion=Accion.ACTUALIZAR,
        entidad="compromiso",
        entidad_id=c.id,
        detalle={"campos": sorted(cambios), "valor_total": c.valor_total},
    )
    db.commit()
    return _detalle_compromiso(db, c)


def anular_compromiso(db: Session, compromiso_id: int, motivo: str) -> CompromisoDetalleOut:
    c = _cargar_compromiso(db, compromiso_id)
    _asegurar_vigente(c)
    c.estado = EstadoCompromiso.ANULADO
    registrar_auditoria(
        db, accion=Accion.ANULAR, entidad="compromiso", entidad_id=c.id, detalle={"motivo": motivo}
    )
    db.commit()
    return _detalle_compromiso(db, c)


def liquidar_compromiso(db: Session, compromiso_id: int) -> CompromisoDetalleOut:
    c = _cargar_compromiso(db, compromiso_id)
    _asegurar_vigente(c)
    c.estado = EstadoCompromiso.LIQUIDADO
    registrar_auditoria(
        db,
        accion=Accion.ACTUALIZAR,
        entidad="compromiso",
        entidad_id=c.id,
        detalle={"operacion": "LIQUIDAR", "valor_total": c.valor_total},
    )
    db.commit()
    return _detalle_compromiso(db, c)


# =====================================================================================
# 5.3 Ejecución
# =====================================================================================
def _validar_periodo(nombre: str, periodo: str | None) -> None:
    if periodo is not None and not es_periodo_valido(periodo):
        raise BusinessRuleError(f"{nombre} inválido: use el formato YYYY-MM", details={nombre: periodo})


def _ejecucion_out(e: Ejecucion) -> EjecucionOut:
    return EjecucionOut(
        id=e.id,
        presupuesto_id=e.presupuesto_id,
        item_id=e.item_id,
        item_codigo=e.item.codigo,
        item_descripcion=e.item.descripcion,
        periodo=e.periodo,
        valor_ejecutado=e.valor_ejecutado,
        cantidad_ejecutada=e.cantidad_ejecutada,
        avance_fisico_pct=e.avance_fisico_pct,
        compromiso_id=e.compromiso_id,
        observacion=e.observacion,
        created_at=e.created_at,
        updated_at=e.updated_at,
        created_by=e.created_by,
        updated_by=e.updated_by,
    )


def listar_ejecucion(
    db: Session,
    *,
    presupuesto_id: int,
    periodo: str | None = None,
    item_id: int | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[EjecucionOut]:
    for nombre, valor in (("periodo", periodo), ("desde", desde), ("hasta", hasta)):
        _validar_periodo(nombre, valor)
    _obtener_presupuesto(db, presupuesto_id)
    stmt = (
        select(Ejecucion)
        .join(EdtNodo, EdtNodo.id == Ejecucion.item_id)
        .where(Ejecucion.presupuesto_id == presupuesto_id)
    )
    if periodo:
        stmt = stmt.where(Ejecucion.periodo == periodo)
    if item_id is not None:
        stmt = stmt.where(Ejecucion.item_id == item_id)
    if desde:
        stmt = stmt.where(Ejecucion.periodo >= desde)
    if hasta:
        stmt = stmt.where(Ejecucion.periodo <= hasta)
    filas = db.scalars(stmt.order_by(Ejecucion.periodo, EdtNodo.codigo)).all()
    return [_ejecucion_out(e) for e in filas]


def listar_periodos(db: Session, presupuesto_id: int) -> list[str]:
    _obtener_presupuesto(db, presupuesto_id)
    return list(
        db.scalars(
            select(Ejecucion.periodo)
            .where(Ejecucion.presupuesto_id == presupuesto_id)
            .distinct()
            .order_by(Ejecucion.periodo)
        ).all()
    )


def guardar_ejecucion(db: Session, lote: EjecucionLote) -> EjecucionLoteResultado:
    """Upsert por (presupuesto, ítem, periodo). Todo o nada ante errores de validación."""
    _validar_periodo("periodo", lote.periodo)
    _obtener_presupuesto(db, lote.presupuesto_id)
    item_ids = [r.item_id for r in lote.registros]
    nodos = {n.id: n for n in db.scalars(select(EdtNodo).where(EdtNodo.id.in_(set(item_ids))))}
    comp_ids = {r.compromiso_id for r in lote.registros if r.compromiso_id is not None}
    compromisos = (
        {c.id: c for c in db.scalars(select(Compromiso).where(Compromiso.id.in_(comp_ids)))}
        if comp_ids
        else {}
    )
    errores: list[dict[str, Any]] = []
    vistos: set[int] = set()
    for i, r in enumerate(lote.registros):
        nodo = nodos.get(r.item_id)
        if nodo is None:
            errores.append({"indice": i, "mensaje": f"El ítem {r.item_id} no existe"})
        elif nodo.nivel is not NivelEdt.ITEM:
            errores.append({"indice": i, "mensaje": f"El nodo {nodo.codigo} no es de nivel ITEM"})
        if r.item_id in vistos:
            errores.append({"indice": i, "mensaje": f"El ítem {r.item_id} está repetido en el lote"})
        vistos.add(r.item_id)
        if r.compromiso_id is not None:
            comp = compromisos.get(r.compromiso_id)
            if comp is None or comp.presupuesto_id != lote.presupuesto_id:
                errores.append(
                    {"indice": i, "mensaje": f"El compromiso {r.compromiso_id} no pertenece al presupuesto"}
                )
    if errores:
        raise BusinessRuleError("Hay registros de ejecución inválidos", details=errores)

    version = version_control_vigente(db, lote.presupuesto_id)
    items_version: set[int] = (
        set(
            db.scalars(
                select(PresupuestoLinea.item_id).where(PresupuestoLinea.version_id == version.id)
            ).all()
        )
        if version
        else set()
    )
    advertencias: list[str] = []
    creados = actualizados = 0
    for r in lote.registros:
        codigo = nodos[r.item_id].codigo
        anterior = db.scalars(
            select(Ejecucion)
            .where(
                Ejecucion.presupuesto_id == lote.presupuesto_id,
                Ejecucion.item_id == r.item_id,
                Ejecucion.periodo < lote.periodo,
            )
            .order_by(Ejecucion.periodo.desc())
            .limit(1)
        ).first()
        if anterior is not None and r.avance_fisico_pct < anterior.avance_fisico_pct:
            advertencias.append(
                f"El avance del ítem {codigo} baja de {anterior.avance_fisico_pct:.2%} "
                f"({anterior.periodo}) a {r.avance_fisico_pct:.2%} ({lote.periodo})"
            )
        if version is not None and r.item_id not in items_version:
            advertencias.append(f"El ítem {codigo} no está en la versión de control {version.numero}")
        e = db.scalars(
            select(Ejecucion).where(
                Ejecucion.presupuesto_id == lote.presupuesto_id,
                Ejecucion.item_id == r.item_id,
                Ejecucion.periodo == lote.periodo,
            )
        ).first()
        if e is None:
            e = Ejecucion(presupuesto_id=lote.presupuesto_id, item_id=r.item_id, periodo=lote.periodo)
            db.add(e)
            creados += 1
        else:
            actualizados += 1
        e.valor_ejecutado = q4(r.valor_ejecutado)
        e.cantidad_ejecutada = q4(r.cantidad_ejecutada) if r.cantidad_ejecutada is not None else None
        e.avance_fisico_pct = r.avance_fisico_pct
        e.compromiso_id = r.compromiso_id
        e.observacion = r.observacion
    if version is None:
        advertencias.append("El presupuesto no tiene una versión APROBADA para validar la ejecución")
    registrar_auditoria(
        db,
        accion=Accion.ACTUALIZAR,
        entidad="ejecucion",
        entidad_id=lote.presupuesto_id,
        detalle={"periodo": lote.periodo, "creados": creados, "actualizados": actualizados},
    )
    db.commit()
    return EjecucionLoteResultado(creados=creados, actualizados=actualizados, advertencias=advertencias)


def eliminar_ejecucion(db: Session, ejecucion_id: int) -> None:
    e = db.get(Ejecucion, ejecucion_id)
    if e is None:
        raise NotFoundError(f"Registro de ejecución {ejecucion_id} no existe")
    registrar_auditoria(
        db,
        accion=Accion.ELIMINAR,
        entidad="ejecucion",
        entidad_id=e.id,
        detalle={"presupuesto_id": e.presupuesto_id, "item_id": e.item_id, "periodo": e.periodo},
    )
    db.delete(e)
    db.commit()


# =====================================================================================
# 5.4 Tablero
# =====================================================================================
@dataclass
class _DatosItem:
    presupuestado: Decimal = ZERO
    comprometido: Decimal = ZERO
    ejecutado: Decimal = ZERO
    avance: Decimal = ZERO


@dataclass
class _DatosTablero:
    version: PresupuestoVersion
    periodo_hasta: str | None
    items: dict[int, _DatosItem]
    nodos: dict[int, EdtNodo]
    capitulos: dict[int, EdtNodo | None]
    serie: list[SerieMensualPunto]


def _resolver_version_tablero(db: Session, presupuesto_id: int, version_id: int | None) -> PresupuestoVersion:
    if version_id is not None:
        v = _obtener_version(db, version_id)
        if v.presupuesto_id != presupuesto_id:
            raise BusinessRuleError(
                f"La versión {version_id} no pertenece al presupuesto {presupuesto_id}",
                details={"version_id": version_id, "presupuesto_id": presupuesto_id},
            )
        return v
    v = version_control_vigente(db, presupuesto_id)
    if v is None:
        raise BusinessRuleError(
            "El presupuesto no tiene versiones APROBADAS para el tablero de control",
            details={"presupuesto_id": presupuesto_id},
        )
    return v


def _datos_tablero(
    db: Session, presupuesto_id: int, version_id: int | None, periodo_hasta: str | None
) -> _DatosTablero:
    _validar_periodo("periodo_hasta", periodo_hasta)
    _obtener_presupuesto(db, presupuesto_id)
    version = _resolver_version_tablero(db, presupuesto_id, version_id)
    items: dict[int, _DatosItem] = defaultdict(_DatosItem)

    for ln in _lineas_version(db, version.id):
        items[ln.item_id].presupuestado += ln.valor_total

    for iid, total in db.execute(
        select(CompromisoLinea.item_id, func.sum(CompromisoLinea.valor_total))
        .join(Compromiso, Compromiso.id == CompromisoLinea.compromiso_id)
        .where(Compromiso.presupuesto_id == presupuesto_id, Compromiso.estado != EstadoCompromiso.ANULADO)
        .group_by(CompromisoLinea.item_id)
    ):
        items[iid].comprometido += Decimal(total or 0)

    filtro_ej = [Ejecucion.presupuesto_id == presupuesto_id]
    if periodo_hasta:
        filtro_ej.append(Ejecucion.periodo <= periodo_hasta)
    vistos_avance: set[int] = set()
    por_periodo: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for iid, periodo, valor, avance in db.execute(
        select(Ejecucion.item_id, Ejecucion.periodo, Ejecucion.valor_ejecutado, Ejecucion.avance_fisico_pct)
        .where(*filtro_ej)
        .order_by(Ejecucion.item_id, Ejecucion.periodo.desc())
    ):
        d = items[iid]
        d.ejecutado += valor
        if iid not in vistos_avance:  # el más reciente (orden desc)
            d.avance = avance
            vistos_avance.add(iid)
        por_periodo[periodo] += valor

    serie: list[SerieMensualPunto] = []
    acumulado = ZERO
    for periodo in sorted(por_periodo):
        acumulado += por_periodo[periodo]
        serie.append(
            SerieMensualPunto(periodo=periodo, ejecutado=por_periodo[periodo], ejecutado_acumulado=acumulado)
        )
    if periodo_hasta is None and serie:
        periodo_hasta = serie[-1].periodo

    nodos, capitulos = _nodos_y_capitulos(db, items.keys())
    return _DatosTablero(version, periodo_hasta, dict(items), nodos, capitulos, serie)


def _fila_tablero(
    id_: int | None, codigo: str, descripcion: str, datos: Iterable[_DatosItem], *, avance_item: bool = False
) -> TableroFila:
    lista = list(datos)
    p = sum((d.presupuestado for d in lista), ZERO)
    c = sum((d.comprometido for d in lista), ZERO)
    e = sum((d.ejecutado for d in lista), ZERO)
    if avance_item:
        avance: Decimal | None = lista[0].avance if lista else ZERO
    else:
        # Promedio del último avance de cada ítem ponderado por su valor presupuestado.
        avance = participacion_pct(sum((d.avance * d.presupuestado for d in lista), ZERO), p)
    return TableroFila(
        id=id_,
        codigo=codigo,
        descripcion=descripcion,
        presupuestado=p,
        comprometido=c,
        ejecutado=e,
        por_comprometer=p - c,
        saldo=p - e,
        pct_comprometido=participacion_pct(c, p),
        pct_ejecutado=participacion_pct(e, p),
        avance_fisico_pct=avance,
    )


def tablero(
    db: Session, presupuesto_id: int, version_id: int | None = None, periodo_hasta: str | None = None
) -> TableroOut:
    t = _datos_tablero(db, presupuesto_id, version_id, periodo_hasta)
    grupos: dict[int | None, list[_DatosItem]] = defaultdict(list)
    for iid, d in t.items.items():
        cap = t.capitulos.get(iid)
        grupos[cap.id if cap else None].append(d)
    filas: list[TableroFila] = []
    for cap_id, datos in grupos.items():
        cap = t.nodos.get(cap_id) if cap_id is not None else None
        filas.append(
            _fila_tablero(
                cap_id,
                cap.codigo if cap else "SIN-CAPITULO",
                cap.descripcion if cap else "Ítems sin capítulo",
                datos,
            )
        )
    filas.sort(key=lambda f: f.codigo)
    return TableroOut(
        presupuesto_id=presupuesto_id,
        version=_version_ref(t.version),
        periodo_hasta=t.periodo_hasta,
        capitulos=filas,
        totales=_fila_tablero(None, "TOTAL", "Total presupuesto", t.items.values()),
        serie_mensual=t.serie,
    )


def tablero_items(
    db: Session,
    presupuesto_id: int,
    version_id: int | None = None,
    capitulo_id: int | None = None,
    periodo_hasta: str | None = None,
) -> list[TableroFila]:
    t = _datos_tablero(db, presupuesto_id, version_id, periodo_hasta)
    filas: list[TableroFila] = []
    for iid, d in t.items.items():
        cap = t.capitulos.get(iid)
        if capitulo_id is not None and (cap is None or cap.id != capitulo_id):
            continue
        nodo = t.nodos[iid]
        filas.append(_fila_tablero(iid, nodo.codigo, nodo.descripcion, [d], avance_item=True))
    return sorted(filas, key=lambda f: f.codigo)


# =====================================================================================
# 5.5 Excel
# =====================================================================================
@dataclass
class ArchivoExcel:
    nombre: str
    contenido: bytes
    media_type: str = xl.XLSX_MEDIA_TYPE


def _slug(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", texto).strip("_") or "archivo"


def plantilla_presupuesto(db: Session) -> ArchivoExcel:
    """Plantilla de importación: hoja ``Presupuesto`` (encabezados exactos) + catálogo de ítems."""
    wb = xl.nuevo_libro()
    ws = wb.create_sheet(xl.HOJA_PLANTILLA)
    anchos = {"codigo_item": 18, "descripcion": 45, "unidad": 10, "observacion": 30}
    xl.escribir_tabla(
        ws,
        [
            xl.Columna(h, "cantidad" if h in ("cantidad", "valor_unitario") else "texto", anchos.get(h, 16))
            for h in xl.ENCABEZADOS_PLANTILLA
        ],
        [],
    )
    ws_items = wb.create_sheet("Items")
    tiene_apu = set(db.scalars(select(Apu.item_id).where(Apu.activo.is_(True))).all())
    items = db.scalars(
        select(EdtNodo)
        .where(EdtNodo.nivel == NivelEdt.ITEM, EdtNodo.activo.is_(True))
        .order_by(EdtNodo.codigo)
    ).all()
    xl.escribir_tabla(
        ws_items,
        [
            xl.Columna("codigo_item", ancho=18),
            xl.Columna("descripcion", ancho=50),
            xl.Columna("unidad", ancho=10),
            xl.Columna("tiene_apu", ancho=10),
        ],
        [
            (
                n.codigo,
                n.descripcion,
                n.unidad.codigo if n.unidad else None,
                "SI" if n.id in tiene_apu else "NO",
            )
            for n in items
        ],
    )
    ws_ins = wb.create_sheet("Instrucciones")
    ws_ins.column_dimensions["A"].width = 110
    for i, texto in enumerate(
        [
            "Plantilla de importación de presupuesto - ERP Prodesa / ADPRO",
            "1. Diligencie la hoja 'Presupuesto' desde la fila 2. No cambie los encabezados de la fila 1.",
            "2. codigo_item: código EDT de nivel ITEM (ver hoja 'Items'). cantidad: obligatoria, >= 0.",
            "3. valor_unitario vacío = se toma del APU del ítem (debe tener APU). Con valor = origen IMPORTADO.",
            "4. descripcion y unidad son informativas (se validan contra el catálogo y generan advertencias).",
            "5. Modo 'agregar' crea o actualiza líneas; modo 'reemplazar' borra las líneas actuales y carga.",
            "6. La importación es todo o nada: si hay un error no se aplica ningún cambio.",
            "Use solo datos de prueba/sintéticos en el prototipo.",
        ],
        start=1,
    ):
        ws_ins.cell(row=i, column=1, value=texto)
    wb.move_sheet("Instrucciones", offset=-2)
    wb.active = wb.sheetnames.index(xl.HOJA_PLANTILLA)
    return ArchivoExcel("plantilla_presupuesto.xlsx", xl.a_bytes(wb))


def importar_presupuesto(
    db: Session,
    version_id: int,
    contenido: bytes,
    *,
    modo: str = "agregar",
    nombre_archivo: str | None = None,
) -> ImportResultado:
    """Importa líneas desde la plantilla. Todo o nada; solo versiones BORRADOR. Audita IMPORTAR.

    Aquí se lee y valida el archivo (errores por fila/columna); la escritura (valorización por
    APU con snapshot o valor IMPORTADO) la hace ``presupuesto.service.aplicar_lineas`` (§6).
    """
    if modo not in ("agregar", "reemplazar"):
        raise BusinessRuleError("modo debe ser 'agregar' o 'reemplazar'")
    version = _obtener_version(db, version_id)
    presupuesto_service.asegurar_editable(version)
    if not contenido:
        raise BusinessRuleError("El archivo está vacío")
    if len(contenido) > MAX_BYTES_IMPORTACION:
        raise BusinessRuleError("El archivo supera el tamaño máximo permitido (10 MB)")
    try:
        lectura = xl.leer_plantilla(contenido)
    except xl.ArchivoInvalidoError as exc:
        raise BusinessRuleError(str(exc)) from exc

    errores = [ImportErrorFila(fila=f, columna=c, mensaje=m) for f, c, m in lectura.errores]
    if not errores and not lectura.filas:
        errores.append(ImportErrorFila(fila=2, columna=None, mensaje="La plantilla no tiene filas de datos"))
    if errores:
        return ImportResultado(aplicado=False, errores=errores)

    codigos = {f.codigo_item for f in lectura.filas if f.codigo_item}
    nodos = {n.codigo: n for n in db.scalars(select(EdtNodo).where(EdtNodo.codigo.in_(codigos)))}
    apus = set(
        db.scalars(
            select(Apu.item_id).where(Apu.item_id.in_([n.id for n in nodos.values()]), Apu.activo.is_(True))
        )
    )
    advertencias: list[str] = []
    validas: list[LineaCreate] = []
    fila_de_valida: list[int] = []  # índice en ``validas`` -> fila del Excel
    vistos: dict[str, int] = {}
    for f in lectura.filas:
        errs_antes = len(errores)
        nodo: EdtNodo | None = None
        if not f.codigo_item:
            errores.append(ImportErrorFila(fila=f.fila, columna="codigo_item", mensaje="Código vacío"))
        else:
            nodo = nodos.get(f.codigo_item)
            if nodo is None:
                errores.append(
                    ImportErrorFila(
                        fila=f.fila,
                        columna="codigo_item",
                        mensaje=f"El ítem {f.codigo_item} no existe en la EDT",
                    )
                )
            elif nodo.nivel is not NivelEdt.ITEM:
                errores.append(
                    ImportErrorFila(
                        fila=f.fila, columna="codigo_item", mensaje=f"{f.codigo_item} no es de nivel ITEM"
                    )
                )
                nodo = None
            elif not nodo.activo:
                errores.append(
                    ImportErrorFila(
                        fila=f.fila, columna="codigo_item", mensaje=f"El ítem {f.codigo_item} está inactivo"
                    )
                )
                nodo = None
            if f.codigo_item in vistos:
                errores.append(
                    ImportErrorFila(
                        fila=f.fila,
                        columna="codigo_item",
                        mensaje=f"El ítem {f.codigo_item} está repetido (fila {vistos[f.codigo_item]})",
                    )
                )
            else:
                vistos[f.codigo_item] = f.fila

        cantidad: Decimal | None = None
        try:
            cantidad = xl.parse_decimal(f.cantidad)
            if cantidad is None:
                errores.append(
                    ImportErrorFila(fila=f.fila, columna="cantidad", mensaje="Cantidad obligatoria")
                )
            elif cantidad < ZERO:
                errores.append(
                    ImportErrorFila(fila=f.fila, columna="cantidad", mensaje="La cantidad debe ser >= 0")
                )
        except ValueError as exc:
            errores.append(
                ImportErrorFila(fila=f.fila, columna="cantidad", mensaje=f"Cantidad no numérica: {exc}")
            )

        valor: Decimal | None = None
        try:
            valor = xl.parse_decimal(f.valor_unitario)
            if valor is not None and valor < ZERO:
                errores.append(
                    ImportErrorFila(
                        fila=f.fila, columna="valor_unitario", mensaje="El valor unitario debe ser >= 0"
                    )
                )
        except ValueError as exc:
            errores.append(
                ImportErrorFila(
                    fila=f.fila, columna="valor_unitario", mensaje=f"Valor unitario no numérico: {exc}"
                )
            )
        if valor is None and nodo is not None and nodo.id not in apus:
            errores.append(
                ImportErrorFila(
                    fila=f.fila,
                    columna="valor_unitario",
                    mensaje=f"El ítem {nodo.codigo} no tiene APU activo; indique valor_unitario",
                )
            )

        if nodo is not None and f.unidad and nodo.unidad and f.unidad.upper() != nodo.unidad.codigo.upper():
            advertencias.append(
                f"Fila {f.fila}: la unidad '{f.unidad}' no coincide con la del ítem {nodo.codigo} "
                f"({nodo.unidad.codigo}); se usa la del catálogo"
            )
        if len(errores) == errs_antes and nodo is not None and cantidad is not None:
            try:
                validas.append(
                    LineaCreate(
                        item_id=nodo.id,
                        cantidad=q4(cantidad),
                        valor_unitario=q4(valor) if valor is not None else None,
                        observacion=f.observacion,
                    )
                )
                fila_de_valida.append(f.fila)
            except ValidationError as exc:
                for e in exc.errors():
                    columna = str(e["loc"][0]) if e.get("loc") else None
                    errores.append(ImportErrorFila(fila=f.fila, columna=columna, mensaje=e["msg"]))

    if errores:
        return ImportResultado(aplicado=False, errores=errores, advertencias=advertencias)

    # --- Aplicar (todo o nada): presupuesto.aplicar_lineas revalida y escribe; commit aquí ---
    try:
        res = presupuesto_service.aplicar_lineas(
            db, version.id, validas, modo=modo, origen_manual=OrigenValor.IMPORTADO, commit=False
        )
    except BusinessRuleError as exc:
        db.rollback()
        detalles = exc.details if isinstance(exc.details, list) else []
        errores = [
            ImportErrorFila(fila=fila_de_valida[d["indice"]], columna="codigo_item", mensaje=d["mensaje"])
            for d in detalles
            if isinstance(d, dict) and isinstance(d.get("indice"), int) and d["indice"] < len(fila_de_valida)
        ] or [ImportErrorFila(fila=2, columna=None, mensaje=exc.message)]
        return ImportResultado(aplicado=False, errores=errores, advertencias=advertencias)
    creadas, actualizadas, eliminadas = res["creadas"], res["actualizadas"], res["eliminadas"]
    sin_precio = db.scalars(
        select(Insumo.codigo)
        .join(PresupuestoLineaInsumo, PresupuestoLineaInsumo.insumo_id == Insumo.id)
        .join(PresupuestoLinea, PresupuestoLinea.id == PresupuestoLineaInsumo.linea_id)
        .where(
            PresupuestoLinea.version_id == version.id,
            PresupuestoLinea.item_id.in_([ln.item_id for ln in validas]),
            PresupuestoLineaInsumo.precio_faltante.is_(True),
        )
        .distinct()
        .order_by(Insumo.codigo)
    ).all()
    if sin_precio:
        advertencias.append("Insumos sin precio vigente (valorizados en 0): " + ", ".join(sin_precio))
    registrar_auditoria(
        db,
        accion=Accion.IMPORTAR,
        entidad="presupuesto_version",
        entidad_id=version.id,
        detalle={
            "modo": modo,
            "archivo": nombre_archivo,
            "creadas": creadas,
            "actualizadas": actualizadas,
            "eliminadas": eliminadas,
        },
    )
    db.commit()
    return ImportResultado(
        aplicado=True,
        lineas_creadas=creadas,
        lineas_actualizadas=actualizadas,
        lineas_eliminadas=eliminadas,
        advertencias=advertencias,
    )


def _nombre_version(v: PresupuestoVersion) -> str:
    return f"{_slug(v.presupuesto.codigo)}_v{v.numero}"


def exportar_presupuesto(db: Session, version_id: int) -> ArchivoExcel:
    """Hojas ``Resumen`` (capítulos + AIU) y ``Presupuesto`` (re-importable: mismas columnas
    iniciales de la plantilla). Capítulos y AIU salen de ``presupuesto.calcular_resumen``."""
    v = _obtener_version(db, version_id)
    resumen = presupuesto_service.calcular_resumen(db, v.id)
    lineas = _lineas_version(db, v.id)
    nodos, caps = _nodos_y_capitulos(db, {ln.item_id for ln in lineas})
    lineas.sort(key=lambda ln: nodos[ln.item_id].codigo)
    costo_directo = resumen.costo_directo

    wb = xl.nuevo_libro()
    ws = wb.create_sheet("Resumen")
    r = xl.escribir_pares(
        ws,
        [
            ("Proyecto", f"{v.presupuesto.proyecto.codigo} - {v.presupuesto.proyecto.nombre}", "texto"),
            ("Presupuesto", f"{v.presupuesto.codigo} - {v.presupuesto.nombre}", "texto"),
            ("Versión", f"{v.numero} - {v.nombre}", "texto"),
            ("Tipo / Estado", f"{v.tipo.value} / {v.estado.value}", "texto"),
            ("Fecha de precios", v.fecha_precios.isoformat(), "texto"),
            ("Ciudad de precios", v.ciudad_precios.codigo if v.ciudad_precios else None, "texto"),
        ],
    )
    filas_cap = [
        (c.codigo, c.descripcion, c.num_lineas, c.valor, participacion_pct(c.valor, costo_directo))
        for c in resumen.capitulos
    ]
    filas_cap.sort(key=lambda f: f[0])
    r = xl.escribir_tabla(
        ws,
        [
            xl.Columna("Capítulo", ancho=28),
            xl.Columna("Descripción", ancho=40),
            xl.Columna("Líneas", "entero", 10),
            xl.Columna("Valor", "pesos", 20),
            xl.Columna("Participación", "pct", 14),
        ],
        filas_cap,
        fila_inicio=r + 2,
        total=("COSTO DIRECTO", None, len(lineas), costo_directo, Decimal(1) if costo_directo else None),
    )
    xl.escribir_pares(
        ws,
        [
            ("Costo directo", resumen.costo_directo, "pesos"),
            (f"Administración ({v.administracion_pct:.2%})", resumen.administracion, "pesos"),
            (f"Imprevistos ({v.imprevistos_pct:.2%})", resumen.imprevistos, "pesos"),
            (f"Utilidad ({v.utilidad_pct:.2%})", resumen.utilidad, "pesos"),
            (f"IVA sobre utilidad ({v.iva_utilidad_pct:.2%})", resumen.iva_utilidad, "pesos"),
            ("Total AIU", resumen.total_aiu, "pesos"),
            ("TOTAL PRESUPUESTO", resumen.total, "pesos"),
        ],
        fila_inicio=r + 2,
    )

    ws_p = wb.create_sheet(xl.HOJA_PLANTILLA)
    xl.escribir_tabla(
        ws_p,
        [
            xl.Columna("codigo_item", ancho=18),
            xl.Columna("descripcion", ancho=45),
            xl.Columna("unidad", ancho=10),
            xl.Columna("cantidad", "cantidad", 16),
            xl.Columna("valor_unitario", "decimal", 18),
            xl.Columna("observacion", ancho=30),
            xl.Columna("valor_total", "pesos", 20),
            xl.Columna("capitulo", ancho=12),
            xl.Columna("origen_unitario", ancho=14),
        ],
        [
            (
                nodos[ln.item_id].codigo,
                nodos[ln.item_id].descripcion,
                nodos[ln.item_id].unidad.codigo if nodos[ln.item_id].unidad else None,
                ln.cantidad,
                ln.valor_unitario,
                ln.observacion,
                ln.valor_total,
                (caps.get(ln.item_id).codigo if caps.get(ln.item_id) else None),  # type: ignore[union-attr]
                ln.origen_unitario,
            )
            for ln in lineas
        ],
        # Sin fila de total: la hoja es re-importable tal cual (el total está en ``Resumen``).
    )
    registrar_auditoria(
        db,
        accion=Accion.EXPORTAR,
        entidad="presupuesto_version",
        entidad_id=v.id,
        detalle={"archivo": "presupuesto"},
    )
    db.commit()
    return ArchivoExcel(f"presupuesto_{_nombre_version(v)}.xlsx", xl.a_bytes(wb))


def exportar_explosion(db: Session, version_id: int) -> ArchivoExcel:
    """Hojas ``Explosion`` (por insumo) y ``PorTipo``, desde ``presupuesto.calcular_explosion``."""
    v = _obtener_version(db, version_id)
    exp = presupuesto_service.calcular_explosion(db, v.id)
    total_insumos = exp.total_insumos

    wb = xl.nuevo_libro()
    ws = wb.create_sheet("Explosion")
    xl.escribir_tabla(
        ws,
        [
            xl.Columna("Código", ancho=16),
            xl.Columna("Insumo", ancho=45),
            xl.Columna("Unidad", ancho=10),
            xl.Columna("Tipo", ancho=8),
            xl.Columna("Cantidad total", "cantidad", 18),
            xl.Columna("Precio medio", "decimal", 18),
            xl.Columna("Valor total", "pesos", 20),
            xl.Columna("Participación", "pct", 14),
        ],
        [
            (
                f.insumo_codigo,
                f.insumo_descripcion,
                f.unidad_codigo,
                f.tipo,
                f.cantidad_total,
                f.precio_unitario,
                f.valor_total,
                participacion_pct(f.valor_total, total_insumos),
            )
            for f in exp.filas
        ],
        total=("TOTAL INSUMOS", None, None, None, None, None, total_insumos, None),
    )
    ws_t = wb.create_sheet("PorTipo")
    por_tipo = {pt.tipo: pt.valor_total for pt in exp.por_tipo}
    r = xl.escribir_tabla(
        ws_t,
        [
            xl.Columna("Tipo", ancho=12),
            xl.Columna("Valor total", "pesos", 20),
            xl.Columna("Participación", "pct", 14),
        ],
        [
            (t, por_tipo[t], participacion_pct(por_tipo[t], total_insumos))
            for t in TipoInsumo
            if t in por_tipo
        ],
        total=("TOTAL INSUMOS", total_insumos, Decimal(1) if total_insumos else None),
    )
    xl.escribir_pares(
        ws_t,
        [
            ("Valor sin desglose (líneas manuales/importadas)", exp.valor_sin_desglose, "pesos"),
            ("Total costo directo", exp.total, "pesos"),
        ],
        fila_inicio=r + 2,
    )
    registrar_auditoria(
        db,
        accion=Accion.EXPORTAR,
        entidad="presupuesto_version",
        entidad_id=v.id,
        detalle={"archivo": "explosion"},
    )
    db.commit()
    return ArchivoExcel(f"explosion_{_nombre_version(v)}.xlsx", xl.a_bytes(wb))


def exportar_comparativo(
    db: Session, base_id: int, comparada_id: int, nivel: NivelComparativo = "item"
) -> ArchivoExcel:
    comp = comparar_versiones(db, base_id, comparada_id, nivel)
    vb = _obtener_version(db, base_id)
    vc = _obtener_version(db, comparada_id)
    wb = xl.nuevo_libro()
    ws = wb.create_sheet("Comparativo")
    r = xl.escribir_pares(
        ws,
        [
            (
                "Versión base",
                f"{vb.presupuesto.codigo} v{vb.numero} - {vb.nombre} ({vb.tipo.value})",
                "texto",
            ),
            (
                "Versión comparada",
                f"{vc.presupuesto.codigo} v{vc.numero} - {vc.nombre} ({vc.tipo.value})",
                "texto",
            ),
            ("Nivel", nivel, "texto"),
        ],
    )
    columnas = [
        xl.Columna("Código", ancho=16),
        xl.Columna("Descripción", ancho=42),
        xl.Columna("Unidad", ancho=9),
        xl.Columna("Tipo", ancho=7),
        xl.Columna("Capítulo", ancho=10),
        xl.Columna("Cant. base", "cantidad", 15),
        xl.Columna("Cant. comparada", "cantidad", 15),
        xl.Columna("Unit. base", "decimal", 16),
        xl.Columna("Unit. comparado", "decimal", 16),
        xl.Columna("Total base", "pesos", 18),
        xl.Columna("Total comparado", "pesos", 18),
        xl.Columna("Dif. cantidad", "cantidad", 15),
        xl.Columna("Dif. unitaria", "decimal", 16),
        xl.Columna("Impacto", "pesos", 18),
        xl.Columna("Variación", "pct", 12),
        xl.Columna("Estado", ancho=12),
    ]
    tot = comp.totales
    xl.escribir_tabla(
        ws,
        columnas,
        [
            (
                f.codigo,
                f.descripcion,
                f.unidad_codigo,
                f.tipo,
                f.capitulo_codigo,
                f.cantidad_base,
                f.cantidad_comparada,
                f.unitario_base,
                f.unitario_comparado,
                f.total_base,
                f.total_comparado,
                f.diferencia_cantidad,
                f.diferencia_unitaria,
                f.impacto,
                f.variacion_pct,
                f.estado,
            )
            for f in comp.filas
        ],
        fila_inicio=r + 2,
        total=(
            "TOTAL",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            tot.total_base,
            tot.total_comparado,
            None,
            None,
            tot.impacto,
            tot.variacion_pct,
            None,
        ),
    )
    ws.freeze_panes = ws.cell(row=r + 3, column=1)
    return ArchivoExcel(
        f"comparativo_{_nombre_version(vb)}_vs_{_nombre_version(vc)}_{nivel}.xlsx", xl.a_bytes(wb)
    )
