"""Lógica de negocio de ADPRO / apu.

Funciones puras respecto a HTTP: reciben ``db: Session`` y datos validados, devuelven modelos
o dataclasses/schemas, y lanzan ``app.core.errors`` (NotFoundError, ConflictError,
BusinessRuleError). Hacen ``db.commit()`` al final de cada operación de escritura y registran
auditoría con ``app.core.audit.registrar_auditoria`` en operaciones relevantes.

Fórmulas: SIEMPRE ``app.modules.adpro.calculos`` y ``app.modules.adpro.valorizacion``
(``valorizar_apu`` aplica ``valor_unitario = Σ cantidad·(1+desperdicio)·precio_vigente``).

Reglas (docs/API_CONTRATO.md §3):
- Un APU por ítem EDT de nivel ITEM (v1). Sin sub-APU (mejora documentada).
- Insumo repetido en un APU → 409; insumo inactivo → 422; ítem no ITEM o inactivo → 422.
- Cambiar un APU NO altera versiones de presupuesto existentes (tienen snapshot).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.audit import Accion, registrar_auditoria
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.modules.adpro.calculos import ZERO, q4
from app.modules.adpro.enums import NivelEdt, TipoInsumo
from app.modules.adpro.models import Apu, ApuInsumo, Ciudad, EdtNodo, Insumo
from app.modules.adpro.valorizacion import ValorizacionApu, valorizar_apu

from . import schemas as s

ENTIDAD = "apu"


# =====================================================================================
# Funciones puras (sin BD) — testeables de forma aislada
# =====================================================================================
def subtotales_por_tipo(componentes: Iterable[tuple[TipoInsumo, Decimal]]) -> dict[str, Decimal]:
    """Suma el aporte al valor unitario por tipo de insumo. Siempre incluye los 5 tipos."""
    out: dict[str, Decimal] = {t.value: ZERO for t in TipoInsumo}
    for tipo, valor in componentes:
        key = tipo.value if isinstance(tipo, TipoInsumo) else str(tipo)
        out[key] = out.get(key, ZERO) + valor
    return {k: q4(v) for k, v in out.items()}


def insumos_duplicados(insumo_ids: Sequence[int]) -> list[int]:
    """Ids que aparecen más de una vez (en orden de primera repetición)."""
    vistos: set[int] = set()
    dup: list[int] = []
    for i in insumo_ids:
        if i in vistos and i not in dup:
            dup.append(i)
        vistos.add(i)
    return dup


# =====================================================================================
# Serialización a schemas del contrato
# =====================================================================================
def apu_insumo_out(ai: ApuInsumo) -> s.ApuInsumoOut:
    ins = ai.insumo
    return s.ApuInsumoOut(
        id=ai.id,
        insumo_id=ai.insumo_id,
        insumo_codigo=ins.codigo,
        insumo_descripcion=ins.descripcion,
        unidad_codigo=ins.unidad.codigo if ins.unidad else None,
        tipo=ins.tipo,
        cantidad=ai.cantidad,
        desperdicio_pct=ai.desperdicio_pct,
        orden=ai.orden,
        observacion=ai.observacion,
    )


def _base_out(apu: Apu) -> dict[str, object]:
    item = apu.item
    return {
        "id": apu.id,
        "item_id": apu.item_id,
        "item_codigo": item.codigo,
        "item_descripcion": item.descripcion,
        "unidad_codigo": item.unidad.codigo if item.unidad else None,
        "descripcion": apu.descripcion,
        "activo": apu.activo,
        "observaciones": apu.observaciones,
        "num_insumos": len(apu.insumos),
        "created_at": apu.created_at,
        "updated_at": apu.updated_at,
        "created_by": apu.created_by,
        "updated_by": apu.updated_by,
    }


def apu_out(apu: Apu) -> s.ApuOut:
    return s.ApuOut(**_base_out(apu))  # type: ignore[arg-type]


def apu_detalle_out(apu: Apu) -> s.ApuDetalleOut:
    return s.ApuDetalleOut(**_base_out(apu), insumos=[apu_insumo_out(ai) for ai in apu.insumos])  # type: ignore[arg-type]


# =====================================================================================
# Consultas
# =====================================================================================
def _stmt_apu():  # type: ignore[no-untyped-def]
    return select(Apu).options(selectinload(Apu.insumos), selectinload(Apu.item))


def obtener_apu(db: Session, apu_id: int) -> Apu:
    apu = db.scalar(_stmt_apu().where(Apu.id == apu_id))
    if apu is None:
        raise NotFoundError(f"APU {apu_id} no existe")
    return apu


def obtener_apu_por_item(db: Session, item_id: int) -> Apu:
    apu = db.scalar(_stmt_apu().where(Apu.item_id == item_id))
    if apu is None:
        raise NotFoundError(f"El ítem {item_id} no tiene APU")
    return apu


def listar_apus(
    db: Session,
    *,
    q: str | None = None,
    capitulo_id: int | None = None,
    activo: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Apu], int]:
    item = aliased(EdtNodo)
    stmt = select(Apu).join(item, item.id == Apu.item_id)
    if q:
        patron = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(item.codigo.ilike(patron), item.descripcion.ilike(patron), Apu.descripcion.ilike(patron))
        )
    if activo is not None:
        stmt = stmt.where(Apu.activo.is_(activo))
    if capitulo_id is not None:
        # Jerarquía estricta ITEM -> GRUPO -> DETALLE -> CAPITULO
        grupo, detalle = aliased(EdtNodo), aliased(EdtNodo)
        stmt = (
            stmt.join(grupo, grupo.id == item.parent_id)
            .join(detalle, detalle.id == grupo.parent_id)
            .where(detalle.parent_id == capitulo_id)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.options(selectinload(Apu.insumos), selectinload(Apu.item))
        .order_by(item.codigo)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), int(total)


# =====================================================================================
# Validaciones
# =====================================================================================
def _validar_item_para_apu(db: Session, item_id: int) -> EdtNodo:
    item = db.get(EdtNodo, item_id)
    if item is None:
        raise NotFoundError(f"Ítem EDT {item_id} no existe")
    if item.nivel is not NivelEdt.ITEM:
        raise BusinessRuleError(
            f"El nodo {item.codigo} es de nivel {item.nivel.value}; solo los ítems pueden tener APU"
        )
    if not item.activo:
        raise BusinessRuleError(f"El ítem {item.codigo} está inactivo")
    existente = db.scalar(select(Apu.id).where(Apu.item_id == item_id))
    if existente is not None:
        raise ConflictError(
            f"El ítem {item.codigo} ya tiene APU (id {existente})", details={"apu_id": existente}
        )
    return item


def _cargar_insumos_validos(db: Session, insumo_ids: Sequence[int]) -> dict[int, Insumo]:
    dup = insumos_duplicados(insumo_ids)
    if dup:
        raise ConflictError("Insumo repetido en el APU", details={"insumo_ids": dup})
    ids = set(insumo_ids)
    if not ids:
        return {}
    encontrados = {i.id: i for i in db.scalars(select(Insumo).where(Insumo.id.in_(ids)))}
    faltantes = sorted(ids - encontrados.keys())
    if faltantes:
        raise NotFoundError("Insumo(s) no existen", details={"insumo_ids": faltantes})
    inactivos = sorted(i for i, ins in encontrados.items() if not ins.activo)
    if inactivos:
        raise BusinessRuleError(
            "No se pueden usar insumos inactivos en un APU", details={"insumo_ids": inactivos}
        )
    return encontrados


def _nuevo_componente(data: s.ApuInsumoIn, orden_def: int) -> ApuInsumo:
    return ApuInsumo(
        insumo_id=data.insumo_id,
        cantidad=data.cantidad,
        desperdicio_pct=data.desperdicio_pct,
        orden=data.orden if data.orden is not None else orden_def,
        observacion=data.observacion,
    )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:  # carrera con otra petición (único apu/insumo)
        db.rollback()
        raise ConflictError("Conflicto de integridad al guardar el APU") from exc


# =====================================================================================
# Escritura
# =====================================================================================
def crear_apu(db: Session, data: s.ApuCreate) -> Apu:
    item = _validar_item_para_apu(db, data.item_id)
    _cargar_insumos_validos(db, [c.insumo_id for c in data.insumos])
    apu = Apu(
        item_id=item.id, descripcion=data.descripcion or item.descripcion, observaciones=data.observaciones
    )
    apu.insumos = [_nuevo_componente(c, i + 1) for i, c in enumerate(data.insumos)]
    db.add(apu)
    db.flush()
    registrar_auditoria(
        db,
        accion=Accion.CREAR,
        entidad=ENTIDAD,
        entidad_id=apu.id,
        detalle={"item_codigo": item.codigo, "num_insumos": len(apu.insumos)},
    )
    _commit(db)
    return obtener_apu(db, apu.id)


def actualizar_apu(db: Session, apu_id: int, data: s.ApuUpdate) -> Apu:
    apu = obtener_apu(db, apu_id)
    for campo, valor in data.model_dump(exclude_unset=True).items():
        if campo == "activo" and valor is None:
            continue
        setattr(apu, campo, valor)
    _commit(db)
    return obtener_apu(db, apu_id)


def reemplazar_insumos(db: Session, apu_id: int, insumos: list[s.ApuInsumoIn]) -> Apu:
    """Reemplaza TODA la composición del APU (PUT .../insumos)."""
    apu = obtener_apu(db, apu_id)
    _cargar_insumos_validos(db, [c.insumo_id for c in insumos])
    antes = len(apu.insumos)
    apu.insumos.clear()
    db.flush()  # borra primero para no chocar con el único (apu_id, insumo_id)
    apu.insumos.extend(_nuevo_componente(c, i + 1) for i, c in enumerate(insumos))
    registrar_auditoria(
        db,
        accion=Accion.ACTUALIZAR,
        entidad=ENTIDAD,
        entidad_id=apu.id,
        detalle={
            "operacion": "reemplazar_composicion",
            "insumos_antes": antes,
            "insumos_despues": len(insumos),
        },
    )
    _commit(db)
    return obtener_apu(db, apu_id)


def agregar_insumo(db: Session, apu_id: int, data: s.ApuInsumoIn) -> ApuInsumo:
    apu = obtener_apu(db, apu_id)
    if any(c.insumo_id == data.insumo_id for c in apu.insumos):
        raise ConflictError("El insumo ya está en el APU", details={"insumo_ids": [data.insumo_id]})
    _cargar_insumos_validos(db, [data.insumo_id])
    orden_def = max((c.orden for c in apu.insumos), default=0) + 1
    comp = _nuevo_componente(data, orden_def)
    apu.insumos.append(comp)
    _commit(db)
    db.refresh(comp)
    return comp


def _obtener_componente(db: Session, apu_id: int, apu_insumo_id: int) -> ApuInsumo:
    comp = db.get(ApuInsumo, apu_insumo_id)
    if comp is None or comp.apu_id != apu_id:
        raise NotFoundError(f"Componente {apu_insumo_id} no existe en el APU {apu_id}")
    return comp


def actualizar_insumo(db: Session, apu_id: int, apu_insumo_id: int, data: s.ApuInsumoUpdate) -> ApuInsumo:
    comp = _obtener_componente(db, apu_id, apu_insumo_id)
    for campo, valor in data.model_dump(exclude_unset=True).items():
        if valor is None and campo in {"cantidad", "desperdicio_pct", "orden"}:
            continue  # campos NOT NULL: None = no cambiar
        setattr(comp, campo, valor)
    _commit(db)
    db.refresh(comp)
    return comp


def eliminar_insumo(db: Session, apu_id: int, apu_insumo_id: int) -> None:
    comp = _obtener_componente(db, apu_id, apu_insumo_id)
    db.delete(comp)
    _commit(db)


def copiar_apu(db: Session, apu_id: int, data: s.ApuCopia) -> Apu:
    origen = obtener_apu(db, apu_id)
    item = _validar_item_para_apu(db, data.item_id_destino)
    nuevo = Apu(
        item_id=item.id,
        descripcion=data.descripcion or origen.descripcion or item.descripcion,
        observaciones=origen.observaciones,
        activo=True,
    )
    nuevo.insumos = [
        ApuInsumo(
            insumo_id=c.insumo_id,
            cantidad=c.cantidad,
            desperdicio_pct=c.desperdicio_pct,
            orden=c.orden,
            observacion=c.observacion,
        )
        for c in origen.insumos
    ]
    db.add(nuevo)
    db.flush()
    registrar_auditoria(
        db,
        accion=Accion.COPIAR,
        entidad=ENTIDAD,
        entidad_id=nuevo.id,
        detalle={"apu_origen_id": origen.id, "item_destino": item.codigo},
    )
    _commit(db)
    return obtener_apu(db, nuevo.id)


# =====================================================================================
# Valorización
# =====================================================================================
def valorizar(db: Session, apu_id: int, ciudad_id: int, fecha: date | None = None) -> s.ValorizacionOut:
    """Valor unitario del APU a una fecha/ciudad con detalle por componente y por tipo."""
    apu = obtener_apu(db, apu_id)
    if db.get(Ciudad, ciudad_id) is None:
        raise NotFoundError(f"Ciudad {ciudad_id} no existe")
    fecha = fecha or date.today()
    val: ValorizacionApu = valorizar_apu(db, apu, ciudad_id, fecha)
    por_insumo = {c.insumo_id: c for c in apu.insumos}
    componentes: list[s.ComponenteOut] = []
    for comp in val.componentes:
        ins = por_insumo[comp.insumo_id].insumo
        componentes.append(
            s.ComponenteOut(
                insumo_id=comp.insumo_id,
                insumo_codigo=ins.codigo,
                insumo_descripcion=ins.descripcion,
                unidad_codigo=ins.unidad.codigo if ins.unidad else None,
                tipo=ins.tipo,
                cantidad=comp.cantidad,
                desperdicio_pct=comp.desperdicio_pct,
                precio_unitario=comp.precio_unitario,
                valor_unitario=comp.valor_unitario,
                precio_faltante=comp.precio_faltante,
                lista_id=comp.lista_id,
            )
        )
    return s.ValorizacionOut(
        apu_id=apu.id,
        item_id=apu.item_id,
        ciudad_id=ciudad_id,
        fecha=fecha,
        valor_unitario=val.valor_unitario,
        insumos_sin_precio=val.insumos_sin_precio,
        subtotales_por_tipo=subtotales_por_tipo((c.tipo, c.valor_unitario) for c in componentes),
        componentes=componentes,
    )
