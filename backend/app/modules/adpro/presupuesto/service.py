"""Lógica de negocio de ADPRO / presupuesto.

Funciones puras respecto a HTTP: reciben ``db: Session`` y datos validados, devuelven modelos
o schemas, y lanzan ``app.core.errors`` (NotFoundError, ConflictError, BusinessRuleError).
Hacen ``db.commit()`` al final de cada operación de escritura y registran auditoría con
``app.core.audit.registrar_auditoria`` (CREAR, APROBAR, CERRAR, COPIAR, RECALCULAR, ELIMINAR).

Fórmulas: SIEMPRE ``app.modules.adpro.calculos`` (redondeo, AIU, explosión) y
``app.modules.adpro.valorizacion`` (precio vigente + valorización de APU).

Estructura del archivo:
1. Funciones de cálculo PURAS (sin BD) — ``explotar_insumos``, ``totales_por_capitulo``,
   ``participacion``, ``totales_version``: testeadas con ejemplos calculados a mano.
2. Guardia de inmutabilidad a nivel ORM (``before_flush``): ninguna escritura sobre líneas,
   snapshot o parámetros de una versión APROBADA/CERRADA llega a la BD, aunque un service
   olvide llamar ``asegurar_editable`` (defensa en profundidad).
3. Contrato interno (API_CONTRATO.md §6): ``obtener_version``, ``asegurar_editable``,
   ``calcular_resumen``, ``calcular_explosion``, ``aplicar_lineas``.
4. Casos de uso (presupuestos, versiones, líneas).

Snapshot: cada línea de origen APU guarda su valor unitario y la composición valorizada
(``PresupuestoLineaInsumo``) al crearse/recalcularse. Al APROBAR se congelan los totales y la
versión queda inmutable: cambios posteriores en APU o listas de precios NO la afectan.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import event, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.audit import Accion, registrar_auditoria
from app.core.db import SESSION_USER_KEY, utcnow
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.query import contiene
from app.modules.adpro.calculos import (
    ZERO,
    ResultadoAIU,
    calcular_aiu,
    cantidad_exacta_insumo,
    participacion_pct,
    q4,
    redondear_pesos,
    valor_total_insumo,
    valor_total_linea,
)
from app.modules.adpro.enums import EstadoVersion, NivelEdt, OrigenValor, TipoInsumo
from app.modules.adpro.models import (
    Apu,
    Ciudad,
    EdtNodo,
    Etapa,
    Insumo,
    Presupuesto,
    PresupuestoLinea,
    PresupuestoLineaInsumo,
    PresupuestoVersion,
    Proyecto,
)
from app.modules.adpro.valorizacion import ValorizacionApu, valorizar_apu

from . import schemas as s

ENT_PRESUPUESTO = "presupuesto"
ENT_VERSION = "presupuesto_version"
ModoAplicar = Literal["agregar", "reemplazar"]
_ModoInterno = Literal["crear", "agregar", "reemplazar"]


# =====================================================================================
# 1. Cálculos PUROS (sin BD)
# =====================================================================================
def participacion(valor: Decimal, total: Decimal) -> Decimal:
    """valor / total como fracción con 6 decimales; 0 si el total es 0 (los schemas de
    presupuesto exigen un número). Delegado en ``calculos.participacion_pct``."""
    return participacion_pct(valor, total) or ZERO


@dataclass(frozen=True)
class FilaSnapshot:
    """Una fila del snapshot de composición de una línea (entrada de la explosión)."""

    insumo_id: int
    cantidad_linea: Decimal
    cantidad_unitaria: Decimal
    desperdicio_pct: Decimal
    precio_unitario: Decimal


@dataclass
class InsumoExplotado:
    insumo_id: int
    cantidad_total: Decimal = ZERO  # q4 de la suma de cantidades EXACTAS
    valor_total: Decimal = ZERO

    @property
    def precio_unitario(self) -> Decimal:
        """Precio medio ponderado = valor_total / cantidad_total (4 decimales)."""
        return ZERO if self.cantidad_total == ZERO else q4(self.valor_total / self.cantidad_total)


def explotar_insumos(filas: Iterable[FilaSnapshot]) -> dict[int, InsumoExplotado]:
    """Explosión de insumos: por cada fila (línea × insumo)

    cantidad = cantidad_exacta_insumo(cant_línea, cant_unitaria, desperdicio)   (sin redondeo)
    valor    = valor_total_insumo(cantidad, precio_snapshot)                     (pesos)

    y se acumulan por insumo. La cantidad acumulada se redondea a 4 decimales UNA vez al final
    (solo para mostrar): valorizar con la cantidad exacta hace que la explosión cuadre con el
    costo directo con diferencias de pocos pesos por redondeo, aun con insumos de precio alto.
    """
    out: dict[int, InsumoExplotado] = {}
    for f in filas:
        cant = cantidad_exacta_insumo(f.cantidad_linea, f.cantidad_unitaria, f.desperdicio_pct)
        acc = out.setdefault(f.insumo_id, InsumoExplotado(f.insumo_id))
        acc.cantidad_total += cant
        acc.valor_total += valor_total_insumo(cant, f.precio_unitario)
    for acc in out.values():
        acc.cantidad_total = q4(acc.cantidad_total)
    return out


@dataclass
class AcumCapitulo:
    clave: Any
    valor: Decimal = ZERO
    num_lineas: int = 0


def totales_por_capitulo(lineas: Iterable[tuple[Any, Decimal]]) -> dict[Any, AcumCapitulo]:
    """Agrupa (clave_capítulo, valor_total_línea) → valor y número de líneas por capítulo."""
    out: dict[Any, AcumCapitulo] = {}
    for clave, valor in lineas:
        acc = out.setdefault(clave, AcumCapitulo(clave))
        acc.valor += valor
        acc.num_lineas += 1
    return out


def totales_version(valores_linea: Iterable[Decimal], version: PresupuestoVersion) -> ResultadoAIU:
    """Costo directo (Σ totales de línea) + AIU + IVA sobre utilidad con los % de la versión."""
    cd = sum(valores_linea, ZERO)
    return calcular_aiu(
        cd,
        version.administracion_pct,
        version.imprevistos_pct,
        version.utilidad_pct,
        version.iva_utilidad_pct,
    )


# =====================================================================================
# 2. Guardia de inmutabilidad (ORM)
# =====================================================================================
_CAMPOS_TRANSICION_CIERRE = {"estado", "cerrado_at", "cerrado_por", "updated_at", "updated_by"}


def _estados_en_bd(session: Session, version_ids: set[int]) -> dict[int, EstadoVersion]:
    """Estado ACTUAL de las versiones leído de la BD (no de la sesión en memoria), con bloqueo de
    fila (``SELECT ... FOR UPDATE``; SQLite lo ignora y ya serializa las escrituras).

    Así una edición que empezó cuando la versión era BORRADOR no se escribe si otro usuario la
    aprobó entretanto (TOCTOU): la aprobación también bloquea la fila antes de congelar totales.
    """
    if not version_ids:
        return {}
    stmt = (
        select(PresupuestoVersion.id, PresupuestoVersion.estado)
        .where(PresupuestoVersion.id.in_(sorted(version_ids)))
        .with_for_update()
    )
    return {vid: EstadoVersion(estado) for vid, estado in session.execute(stmt)}


def _version_de(session: Session, obj: Any) -> PresupuestoVersion | None:
    if isinstance(obj, PresupuestoVersion):
        return obj
    if isinstance(obj, PresupuestoLinea):
        if "version" in obj.__dict__ and obj.__dict__["version"] is not None:
            return obj.__dict__["version"]
        return session.get(PresupuestoVersion, obj.version_id) if obj.version_id else None
    if isinstance(obj, PresupuestoLineaInsumo):
        linea = obj.__dict__.get("linea")
        if linea is None and obj.linea_id:
            linea = session.get(PresupuestoLinea, obj.linea_id)
        return _version_de(session, linea) if linea is not None else None
    return None


def _cambios_columnas(obj: Any) -> set[str]:
    st = inspect(obj)
    return {a.key for a in st.mapper.column_attrs if st.attrs[a.key].history.has_changes()}


@event.listens_for(Session, "before_flush")
def _guardia_inmutabilidad(session: Session, _ctx: Any, _instances: Any) -> None:
    with session.no_autoflush:
        pares: list[tuple[Any, PresupuestoVersion]] = []
        for obj in list(session.new) + list(session.dirty) + list(session.deleted):
            if not isinstance(obj, PresupuestoVersion | PresupuestoLinea | PresupuestoLineaInsumo):
                continue
            version = _version_de(session, obj)
            if version is None or version.id is None or inspect(version).pending:
                continue  # versión nueva: aún no existe en la BD
            pares.append((obj, version))
        if not pares:
            return
        estados = _estados_en_bd(session, {v.id for _, v in pares})
        for obj, version in pares:
            estado = estados.get(version.id)
            if estado is None or estado.editable:
                continue
            if obj is version and obj not in session.deleted:
                cambios = _cambios_columnas(obj)
                if not cambios:
                    continue
                if (
                    estado is EstadoVersion.APROBADO
                    and version.estado is EstadoVersion.CERRADO
                    and cambios <= _CAMPOS_TRANSICION_CIERRE
                ):
                    continue  # única transición permitida: APROBADO -> CERRADO
            elif obj in session.dirty and not _cambios_columnas(obj):
                continue  # solo cambió una colección/relación sin columnas
            raise BusinessRuleError(
                f"La versión {version.id} está {estado.value} y es inmutable",
                details={"version_id": version.id, "estado": estado.value},
            )


# =====================================================================================
# 3. Contrato interno (usado por control)
# =====================================================================================
def obtener_version(db: Session, version_id: int) -> PresupuestoVersion:
    version = db.get(PresupuestoVersion, version_id)
    if version is None:
        raise NotFoundError(f"Versión de presupuesto {version_id} no existe")
    return version


def obtener_version_para_escritura(db: Session, version_id: int) -> PresupuestoVersion:
    """Carga la versión desde la BD con bloqueo de fila (``FOR UPDATE`` en PostgreSQL) y
    refresca la instancia de la sesión. Toda operación que escribe en una versión (líneas,
    snapshot, parámetros, aprobar, cerrar) valida el estado sobre ESTA lectura, de modo que dos
    transacciones concurrentes (editar línea vs. aprobar) quedan serializadas."""
    version = db.scalar(
        select(PresupuestoVersion)
        .where(PresupuestoVersion.id == version_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if version is None:
        raise NotFoundError(f"Versión de presupuesto {version_id} no existe")
    return version


def asegurar_editable(version: PresupuestoVersion) -> None:
    if not version.estado.editable:
        raise BusinessRuleError(
            f"La versión {version.numero} está {version.estado.value}: no se puede modificar. "
            "Cópiela para crear un nuevo borrador.",
            details={"version_id": version.id, "estado": version.estado.value},
        )


def _lineas_con_snapshot(db: Session, version_id: int) -> list[PresupuestoLinea]:
    return list(
        db.scalars(
            select(PresupuestoLinea)
            .where(PresupuestoLinea.version_id == version_id)
            .options(selectinload(PresupuestoLinea.insumos))
        )
    )


def capitulos_de_items(db: Session, item_ids: Iterable[int]) -> dict[int, EdtNodo | None]:
    """Capítulo de cada ítem (ITEM -> GRUPO -> DETALLE -> CAPITULO) en una sola consulta."""
    ids = sorted(set(item_ids))
    if not ids:
        return {}
    item, grupo, detalle, cap = (aliased(EdtNodo) for _ in range(4))
    stmt = (
        select(item.id, cap)
        .select_from(item)
        .outerjoin(grupo, grupo.id == item.parent_id)
        .outerjoin(detalle, detalle.id == grupo.parent_id)
        .outerjoin(cap, (cap.id == detalle.parent_id) & (cap.nivel == NivelEdt.CAPITULO))
        .where(item.id.in_(ids))
    )
    return {iid: c for iid, c in db.execute(stmt)}


def calcular_resumen(db: Session, version_id: int) -> s.ResumenOut:
    version = obtener_version(db, version_id)
    lineas = _lineas_con_snapshot(db, version_id)
    caps = capitulos_de_items(db, (ln.item_id for ln in lineas))
    acum = totales_por_capitulo((caps.get(ln.item_id), ln.valor_total) for ln in lineas)
    aiu = totales_version((ln.valor_total for ln in lineas), version)
    capitulos = [
        s.CapituloTotal(
            capitulo_id=cap.id if cap else None,
            codigo=cap.codigo if cap else "SIN-CAPITULO",
            descripcion=cap.descripcion if cap else "Ítems sin capítulo",
            valor=a.valor,
            participacion_pct=participacion(a.valor, aiu.costo_directo),
            num_lineas=a.num_lineas,
        )
        for cap, a in acum.items()
    ]
    capitulos.sort(key=lambda c: c.codigo)
    return s.ResumenOut(
        version_id=version.id,
        capitulos=capitulos,
        costo_directo=aiu.costo_directo,
        administracion_pct=version.administracion_pct,
        imprevistos_pct=version.imprevistos_pct,
        utilidad_pct=version.utilidad_pct,
        iva_utilidad_pct=version.iva_utilidad_pct,
        administracion=aiu.administracion,
        imprevistos=aiu.imprevistos,
        utilidad=aiu.utilidad,
        iva_utilidad=aiu.iva_utilidad,
        total_aiu=aiu.total_aiu,
        total=aiu.total,
        num_lineas=len(lineas),
        lineas_sin_precio=sum(1 for ln in lineas if any(li.precio_faltante for li in ln.insumos)),
    )


def calcular_explosion(db: Session, version_id: int, tipo: TipoInsumo | None = None) -> s.ExplosionOut:
    """Explosión de insumos desde el snapshot. Con ``tipo`` filtra filas y ``por_tipo``;
    ``valor_sin_desglose`` (líneas sin snapshot) siempre se reporta completo para cuadrar."""
    obtener_version(db, version_id)
    lineas = _lineas_con_snapshot(db, version_id)
    filas_snap = [
        FilaSnapshot(li.insumo_id, ln.cantidad, li.cantidad_unitaria, li.desperdicio_pct, li.precio_unitario)
        for ln in lineas
        for li in ln.insumos
    ]
    explotado = explotar_insumos(filas_snap)
    insumos = (
        {i.id: i for i in db.scalars(select(Insumo).where(Insumo.id.in_(explotado.keys())))}
        if explotado
        else {}
    )
    if tipo is not None:
        explotado = {k: v for k, v in explotado.items() if insumos[k].tipo is tipo}
    total_insumos = sum((e.valor_total for e in explotado.values()), ZERO)
    filas = [
        s.ExplosionFila(
            insumo_id=e.insumo_id,
            insumo_codigo=insumos[e.insumo_id].codigo,
            insumo_descripcion=insumos[e.insumo_id].descripcion,
            unidad_codigo=insumos[e.insumo_id].unidad.codigo if insumos[e.insumo_id].unidad else None,
            tipo=insumos[e.insumo_id].tipo,
            cantidad_total=q4(e.cantidad_total),
            precio_unitario=e.precio_unitario,
            valor_total=e.valor_total,
            participacion_pct=participacion(e.valor_total, total_insumos),
        )
        for e in explotado.values()
    ]
    filas.sort(key=lambda f: f.insumo_codigo)
    por_tipo_acc: dict[TipoInsumo, Decimal] = defaultdict(lambda: ZERO)
    for f in filas:
        por_tipo_acc[f.tipo] += f.valor_total
    por_tipo = [
        s.ExplosionTipo(tipo=t, valor_total=v, participacion_pct=participacion(v, total_insumos))
        for t, v in sorted(por_tipo_acc.items(), key=lambda kv: list(TipoInsumo).index(kv[0]))
    ]
    sin_desglose = sum((ln.valor_total for ln in lineas if not ln.insumos), ZERO)
    return s.ExplosionOut(
        version_id=version_id,
        filas=filas,
        por_tipo=por_tipo,
        total_insumos=total_insumos,
        valor_sin_desglose=sin_desglose,
        total=total_insumos + sin_desglose,
    )


def _apus_por_item(db: Session, item_ids: Iterable[int]) -> dict[int, Apu]:
    """APU ACTIVO de cada ítem. Un APU inactivo no valoriza (crear, importar, recalcular, copiar)."""
    ids = sorted(set(item_ids))
    if not ids:
        return {}
    apus = db.scalars(
        select(Apu).where(Apu.item_id.in_(ids), Apu.activo.is_(True)).options(selectinload(Apu.insumos))
    )
    return {a.item_id: a for a in apus}


def _reemplazar_snapshot(db: Session, linea: PresupuestoLinea, val: ValorizacionApu | None) -> None:
    """Regenera el snapshot de composición de la línea (o lo borra si ``val`` es None)."""
    if linea.insumos:
        linea.insumos.clear()
        db.flush()  # borrar antes de insertar: único (linea_id, insumo_id)
    if val is None:
        return
    linea.insumos.extend(
        PresupuestoLineaInsumo(
            insumo_id=c.insumo_id,
            cantidad_unitaria=c.cantidad,
            desperdicio_pct=c.desperdicio_pct,
            precio_unitario=c.precio_unitario,
            valor_unitario=c.valor_unitario,
            precio_faltante=c.precio_faltante,
        )
        for c in val.componentes
    )


def _valorizar_linea_apu(
    db: Session, version: PresupuestoVersion, linea: PresupuestoLinea, apu: Apu, fecha: date | None = None
) -> ValorizacionApu:
    val = valorizar_apu(db, apu, version.ciudad_precios_id, fecha or version.fecha_precios)
    linea.valor_unitario = val.valor_unitario
    linea.origen_unitario = OrigenValor.APU
    linea.valor_total = valor_total_linea(linea.cantidad, linea.valor_unitario)
    _reemplazar_snapshot(db, linea, val)
    return val


def _valor_manual(db: Session, linea: PresupuestoLinea, valor: Decimal, origen: OrigenValor) -> None:
    linea.valor_unitario = q4(valor)
    linea.origen_unitario = origen
    linea.valor_total = valor_total_linea(linea.cantidad, linea.valor_unitario)
    _reemplazar_snapshot(db, linea, None)


def _aplicar(
    db: Session,
    version: PresupuestoVersion,
    lineas: Sequence[s.LineaCreate],
    *,
    modo: _ModoInterno,
    origen_manual: OrigenValor,
) -> dict[str, int]:
    """Valida TODO primero (todo o nada) y luego aplica. Lanza BusinessRuleError con
    ``details = [{indice, mensaje}]`` si alguna línea es inválida."""
    asegurar_editable(version)
    existentes = (
        {} if modo == "reemplazar" else {ln.item_id: ln for ln in _lineas_con_snapshot(db, version.id)}
    )
    item_ids = [ln.item_id for ln in lineas]
    items = {i.id: i for i in db.scalars(select(EdtNodo).where(EdtNodo.id.in_(set(item_ids))))}
    apus = _apus_por_item(db, item_ids)

    errores: list[dict[str, Any]] = []
    vistos: set[int] = set()
    for idx, ln in enumerate(lineas):
        item = items.get(ln.item_id)
        msg: str | None = None
        if item is None:
            msg = f"El ítem {ln.item_id} no existe"
        elif item.nivel is not NivelEdt.ITEM:
            msg = f"{item.codigo} es {item.nivel.value}; solo se presupuestan ítems"
        elif not item.activo:
            msg = f"El ítem {item.codigo} está inactivo"
        elif ln.item_id in vistos:
            msg = f"El ítem {item.codigo} está repetido en la solicitud"
        elif modo == "crear" and ln.item_id in existentes:
            msg = f"El ítem {item.codigo} ya existe en la versión"
        elif ln.valor_unitario is None and ln.item_id not in apus:
            msg = f"El ítem {item.codigo} no tiene APU activo; indique valor_unitario"
        if msg:
            errores.append({"indice": idx, "mensaje": msg})
        vistos.add(ln.item_id)
    if errores:
        raise BusinessRuleError(
            f"{len(errores)} línea(s) con errores; no se aplicó ningún cambio", details=errores
        )

    eliminadas = 0
    if modo == "reemplazar":
        actuales = list(db.scalars(select(PresupuestoLinea).where(PresupuestoLinea.version_id == version.id)))
        eliminadas = len(actuales)
        for ln_db in actuales:
            db.delete(ln_db)
        db.flush()
        orden = 0
    else:
        orden = max((ln.orden for ln in existentes.values()), default=0)

    creadas = actualizadas = 0
    for ln in lineas:
        linea = existentes.get(ln.item_id)
        if linea is None:
            orden += 1
            linea = PresupuestoLinea(
                version_id=version.id, item_id=ln.item_id, cantidad=ln.cantidad, orden=orden
            )
            linea.insumos = []
            db.add(linea)
            creadas += 1
        else:
            linea.cantidad = ln.cantidad
            actualizadas += 1
        if ln.observacion is not None:
            linea.observacion = ln.observacion
        if ln.valor_unitario is not None:
            _valor_manual(db, linea, ln.valor_unitario, origen_manual)
        else:
            _valorizar_linea_apu(db, version, linea, apus[ln.item_id])
    db.flush()
    return {"creadas": creadas, "actualizadas": actualizadas, "eliminadas": eliminadas}


def aplicar_lineas(
    db: Session,
    version_id: int,
    lineas: list[s.LineaCreate],
    *,
    modo: ModoAplicar,
    origen_manual: OrigenValor = OrigenValor.MANUAL,
    commit: bool = True,
) -> dict[str, int]:
    """Carga masiva (importación Excel). ``agregar``: crea nuevas y actualiza existentes;
    ``reemplazar``: borra todas las líneas y carga. Todo o nada."""
    if modo not in ("agregar", "reemplazar"):
        raise BusinessRuleError(f"Modo inválido: {modo}")
    version = obtener_version_para_escritura(db, version_id)
    # La validación ocurre antes de mutar nada: si lanza, la sesión queda intacta.
    res = _aplicar(db, version, lineas, modo=modo, origen_manual=origen_manual)
    if commit:
        _commit(db)
    return res


# =====================================================================================
# 4. Casos de uso
# =====================================================================================
def _usuario(db: Session) -> str:
    return str(db.info.get(SESSION_USER_KEY) or "sistema")


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Conflicto de integridad (registro duplicado o referencia inválida)") from exc
    except Exception:
        db.rollback()
        raise


# --- Presupuestos ----------------------------------------------------------------------
def obtener_presupuesto(db: Session, presupuesto_id: int) -> Presupuesto:
    p = db.scalar(
        select(Presupuesto)
        .where(Presupuesto.id == presupuesto_id)
        .options(selectinload(Presupuesto.versiones), selectinload(Presupuesto.proyecto))
    )
    if p is None:
        raise NotFoundError(f"Presupuesto {presupuesto_id} no existe")
    return p


def listar_presupuestos(
    db: Session, *, proyecto_id: int | None = None, q: str | None = None
) -> list[Presupuesto]:
    stmt = select(Presupuesto).options(
        selectinload(Presupuesto.versiones), selectinload(Presupuesto.proyecto)
    )
    if proyecto_id is not None:
        stmt = stmt.where(Presupuesto.proyecto_id == proyecto_id)
    if q:
        stmt = stmt.where(contiene(Presupuesto.codigo, q) | contiene(Presupuesto.nombre, q))
    return list(db.scalars(stmt.order_by(Presupuesto.proyecto_id, Presupuesto.codigo)))


def crear_presupuesto(db: Session, data: s.PresupuestoCreate) -> Presupuesto:
    if db.get(Proyecto, data.proyecto_id) is None:
        raise NotFoundError(f"Proyecto {data.proyecto_id} no existe")
    if data.etapa_id is not None:
        etapa = db.get(Etapa, data.etapa_id)
        if etapa is None:
            raise NotFoundError(f"Etapa {data.etapa_id} no existe")
        if etapa.proyecto_id != data.proyecto_id:
            raise BusinessRuleError("La etapa no pertenece al proyecto")
    codigo = data.codigo.strip().upper()
    dup = db.scalar(
        select(Presupuesto.id).where(
            Presupuesto.proyecto_id == data.proyecto_id, Presupuesto.codigo == codigo
        )
    )
    if dup is not None:
        raise ConflictError(f"Ya existe el presupuesto {codigo} en el proyecto")
    p = Presupuesto(
        proyecto_id=data.proyecto_id,
        etapa_id=data.etapa_id,
        codigo=codigo,
        nombre=data.nombre.strip(),
        descripcion=data.descripcion,
    )
    db.add(p)
    db.flush()
    registrar_auditoria(
        db, accion=Accion.CREAR, entidad=ENT_PRESUPUESTO, entidad_id=p.id, detalle={"codigo": codigo}
    )
    _commit(db)
    return obtener_presupuesto(db, p.id)


def actualizar_presupuesto(db: Session, presupuesto_id: int, data: s.PresupuestoUpdate) -> Presupuesto:
    p = obtener_presupuesto(db, presupuesto_id)
    cambios = data.model_dump(exclude_unset=True)
    if cambios.get("nombre") is not None:
        p.nombre = cambios["nombre"].strip()
    if "descripcion" in cambios:
        p.descripcion = cambios["descripcion"]
    _commit(db)
    return obtener_presupuesto(db, presupuesto_id)


def _resumen_lineas(db: Session, version_ids: Sequence[int]) -> dict[int, list[Decimal]]:
    """valores totales de línea por versión (suma en Python para exactitud Decimal)."""
    out: dict[int, list[Decimal]] = {vid: [] for vid in version_ids}
    if not version_ids:
        return out
    rows = db.execute(
        select(PresupuestoLinea.version_id, PresupuestoLinea.valor_total).where(
            PresupuestoLinea.version_id.in_(version_ids)
        )
    )
    for vid, valor in rows:
        out[vid].append(Decimal(valor))
    return out


def version_out(
    db: Session, version: PresupuestoVersion, valores: list[Decimal] | None = None
) -> s.VersionOut:
    if valores is None:
        valores = _resumen_lineas(db, [version.id])[version.id]
    if version.estado.editable or version.total_costo_directo is None:
        aiu = totales_version(valores, version)
        cd, total = aiu.costo_directo, aiu.total
    else:  # congelados al aprobar
        cd = redondear_pesos(version.total_costo_directo)
        total = redondear_pesos(version.total_presupuesto or ZERO)
    ciudad = db.get(Ciudad, version.ciudad_precios_id)
    return s.VersionOut(
        id=version.id,
        presupuesto_id=version.presupuesto_id,
        numero=version.numero,
        tipo=version.tipo,
        estado=version.estado,
        nombre=version.nombre,
        descripcion=version.descripcion,
        fecha_precios=version.fecha_precios,
        ciudad_precios_id=version.ciudad_precios_id,
        ciudad_precios_codigo=ciudad.codigo if ciudad else None,
        administracion_pct=version.administracion_pct,
        imprevistos_pct=version.imprevistos_pct,
        utilidad_pct=version.utilidad_pct,
        iva_utilidad_pct=version.iva_utilidad_pct,
        version_origen_id=version.version_origen_id,
        aprobado_at=version.aprobado_at,
        aprobado_por=version.aprobado_por,
        cerrado_at=version.cerrado_at,
        cerrado_por=version.cerrado_por,
        total_costo_directo=cd,
        total_presupuesto=total,
        num_lineas=len(valores),
        editable=version.estado.editable,
        created_at=version.created_at,
        updated_at=version.updated_at,
        created_by=version.created_by,
        updated_by=version.updated_by,
    )


def _presupuesto_base(p: Presupuesto) -> dict[str, Any]:
    return {
        "id": p.id,
        "proyecto_id": p.proyecto_id,
        "proyecto_codigo": p.proyecto.codigo,
        "proyecto_nombre": p.proyecto.nombre,
        "etapa_id": p.etapa_id,
        "etapa_codigo": p.etapa.codigo if p.etapa else None,
        "codigo": p.codigo,
        "nombre": p.nombre,
        "descripcion": p.descripcion,
        "num_versiones": len(p.versiones),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "created_by": p.created_by,
        "updated_by": p.updated_by,
    }


def presupuesto_out(p: Presupuesto) -> s.PresupuestoOut:
    return s.PresupuestoOut(**_presupuesto_base(p))


def presupuesto_detalle_out(db: Session, p: Presupuesto) -> s.PresupuestoDetalleOut:
    valores = _resumen_lineas(db, [v.id for v in p.versiones])
    versiones = [version_out(db, v, valores[v.id]) for v in sorted(p.versiones, key=lambda v: v.numero)]
    return s.PresupuestoDetalleOut(**_presupuesto_base(p), versiones=versiones)


# --- Versiones --------------------------------------------------------------------------
def _siguiente_numero(db: Session, presupuesto_id: int) -> int:
    actual = db.scalar(
        select(func.max(PresupuestoVersion.numero)).where(PresupuestoVersion.presupuesto_id == presupuesto_id)
    )
    return int(actual or 0) + 1


def _validar_ciudad(db: Session, ciudad_id: int) -> None:
    if db.get(Ciudad, ciudad_id) is None:
        raise NotFoundError(f"Ciudad {ciudad_id} no existe")


def crear_version(db: Session, presupuesto_id: int, data: s.VersionCreate) -> PresupuestoVersion:
    p = obtener_presupuesto(db, presupuesto_id)
    ciudad_id = data.ciudad_precios_id or p.proyecto.ciudad_id
    _validar_ciudad(db, ciudad_id)
    v = PresupuestoVersion(
        presupuesto_id=p.id,
        numero=_siguiente_numero(db, p.id),
        tipo=data.tipo,
        estado=EstadoVersion.BORRADOR,
        nombre=data.nombre.strip(),
        descripcion=data.descripcion,
        fecha_precios=data.fecha_precios,
        ciudad_precios_id=ciudad_id,
        administracion_pct=data.administracion_pct,
        imprevistos_pct=data.imprevistos_pct,
        utilidad_pct=data.utilidad_pct,
        iva_utilidad_pct=data.iva_utilidad_pct,
    )
    db.add(v)
    db.flush()
    registrar_auditoria(
        db,
        accion=Accion.CREAR,
        entidad=ENT_VERSION,
        entidad_id=v.id,
        detalle={"presupuesto_id": p.id, "numero": v.numero, "tipo": v.tipo},
    )
    _commit(db)
    return v


def actualizar_version(db: Session, version_id: int, data: s.VersionUpdate) -> PresupuestoVersion:
    v = obtener_version_para_escritura(db, version_id)
    asegurar_editable(v)
    cambios = data.model_dump(exclude_unset=True)
    if cambios.get("ciudad_precios_id") is not None:
        _validar_ciudad(db, cambios["ciudad_precios_id"])
    for campo, valor in cambios.items():
        if valor is None and campo != "descripcion":
            continue  # columnas NOT NULL: None = no cambiar
        setattr(v, campo, valor.strip() if campo == "nombre" else valor)
    _commit(db)
    return v


def eliminar_version(db: Session, version_id: int) -> None:
    v = obtener_version_para_escritura(db, version_id)
    asegurar_editable(v)
    registrar_auditoria(
        db,
        accion=Accion.ELIMINAR,
        entidad=ENT_VERSION,
        entidad_id=v.id,
        detalle={"presupuesto_id": v.presupuesto_id, "numero": v.numero},
    )
    db.delete(v)
    _commit(db)


def aprobar_version(db: Session, version_id: int, observacion: str | None = None) -> PresupuestoVersion:
    """BORRADOR -> APROBADO. Congela totales; desde aquí líneas y snapshot son inmutables.
    Bloquea la versión antes de leer las líneas: los totales congelados cuadran con ellas."""
    v = obtener_version_para_escritura(db, version_id)
    if v.estado is not EstadoVersion.BORRADOR:
        raise BusinessRuleError(f"Solo se aprueban versiones BORRADOR (estado actual: {v.estado.value})")
    lineas = _lineas_con_snapshot(db, v.id)
    if not lineas:
        raise BusinessRuleError("No se puede aprobar una versión sin líneas")
    aiu = totales_version((ln.valor_total for ln in lineas), v)
    v.total_costo_directo = aiu.costo_directo
    v.total_presupuesto = aiu.total
    v.estado = EstadoVersion.APROBADO
    v.aprobado_at = utcnow()
    v.aprobado_por = _usuario(db)
    registrar_auditoria(
        db,
        accion=Accion.APROBAR,
        entidad=ENT_VERSION,
        entidad_id=v.id,
        detalle={
            "total_costo_directo": aiu.costo_directo,
            "total_presupuesto": aiu.total,
            "num_lineas": len(lineas),
            "lineas_sin_precio": sum(1 for ln in lineas if any(li.precio_faltante for li in ln.insumos)),
            "observacion": observacion,
        },
    )
    _commit(db)
    return v


def cerrar_version(db: Session, version_id: int, observacion: str | None = None) -> PresupuestoVersion:
    v = obtener_version_para_escritura(db, version_id)
    if v.estado is not EstadoVersion.APROBADO:
        raise BusinessRuleError(f"Solo se cierran versiones APROBADAS (estado actual: {v.estado.value})")
    v.estado = EstadoVersion.CERRADO
    v.cerrado_at = utcnow()
    v.cerrado_por = _usuario(db)
    registrar_auditoria(
        db, accion=Accion.CERRAR, entidad=ENT_VERSION, entidad_id=v.id, detalle={"observacion": observacion}
    )
    _commit(db)
    return v


def copiar_version(db: Session, version_id: int, data: s.VersionCopy) -> PresupuestoVersion:
    """Crea un BORRADOR copiando AIU, líneas y snapshot. Opcionalmente revaloriza las líneas
    de origen APU a ``fecha_precios`` (o a la fecha de la versión origen)."""
    origen = obtener_version(db, version_id)
    destino_id = data.presupuesto_id_destino or origen.presupuesto_id
    obtener_presupuesto(db, destino_id)
    nueva = PresupuestoVersion(
        presupuesto_id=destino_id,
        numero=_siguiente_numero(db, destino_id),
        tipo=data.tipo,
        estado=EstadoVersion.BORRADOR,
        nombre=data.nombre.strip(),
        descripcion=data.descripcion,
        fecha_precios=data.fecha_precios or origen.fecha_precios,
        ciudad_precios_id=origen.ciudad_precios_id,
        administracion_pct=origen.administracion_pct,
        imprevistos_pct=origen.imprevistos_pct,
        utilidad_pct=origen.utilidad_pct,
        iva_utilidad_pct=origen.iva_utilidad_pct,
        version_origen_id=origen.id,
    )
    db.add(nueva)
    db.flush()
    lineas_origen = _lineas_con_snapshot(db, origen.id)
    apus = _apus_por_item(db, (ln.item_id for ln in lineas_origen)) if data.recalcular_precios else {}
    revalorizadas = 0
    sin_apu: list[int] = []
    for lo in lineas_origen:
        ln = PresupuestoLinea(
            version_id=nueva.id,
            item_id=lo.item_id,
            cantidad=lo.cantidad,
            valor_unitario=lo.valor_unitario,
            valor_total=lo.valor_total,
            origen_unitario=lo.origen_unitario,
            orden=lo.orden,
            observacion=lo.observacion,
        )
        ln.insumos = [
            PresupuestoLineaInsumo(
                insumo_id=li.insumo_id,
                cantidad_unitaria=li.cantidad_unitaria,
                desperdicio_pct=li.desperdicio_pct,
                precio_unitario=li.precio_unitario,
                valor_unitario=li.valor_unitario,
                precio_faltante=li.precio_faltante,
            )
            for li in lo.insumos
        ]
        db.add(ln)
        apu = apus.get(lo.item_id)
        if data.recalcular_precios and lo.origen_unitario is OrigenValor.APU:
            if apu is None:  # sin APU activo: conserva el valor y snapshot de la versión origen
                sin_apu.append(lo.item_id)
                continue
            db.flush()
            _valorizar_linea_apu(db, nueva, ln, apu)
            revalorizadas += 1
    db.flush()
    registrar_auditoria(
        db,
        accion=Accion.COPIAR,
        entidad=ENT_VERSION,
        entidad_id=nueva.id,
        detalle={
            "version_origen_id": origen.id,
            "presupuesto_destino_id": destino_id,
            "lineas": len(lineas_origen),
            "recalcular_precios": data.recalcular_precios,
            "lineas_revalorizadas": revalorizadas,
            "items_sin_apu": sin_apu,
            "fecha_precios": nueva.fecha_precios,
        },
    )
    _commit(db)
    return nueva


def recalcular_version(db: Session, version_id: int) -> s.RecalculoOut:
    """Revaloriza las líneas de origen APU con el APU y precios vigentes (solo BORRADOR)."""
    v = obtener_version_para_escritura(db, version_id)
    asegurar_editable(v)
    lineas = _lineas_con_snapshot(db, v.id)
    apus = _apus_por_item(db, (ln.item_id for ln in lineas))
    sin_precio: set[int] = set()
    n = 0
    sin_apu: list[int] = []
    for ln in lineas:
        if ln.origen_unitario is not OrigenValor.APU:
            continue
        apu = apus.get(ln.item_id)
        if apu is None:
            sin_apu.append(ln.item_id)
            continue
        val = _valorizar_linea_apu(db, v, ln, apu)
        sin_precio.update(val.insumos_sin_precio)
        n += 1
    db.flush()
    total_cd = redondear_pesos(sum((ln.valor_total for ln in lineas), ZERO))
    sin_apu = sorted(set(sin_apu))
    registrar_auditoria(
        db,
        accion=Accion.RECALCULAR,
        entidad=ENT_VERSION,
        entidad_id=v.id,
        detalle={
            "lineas_recalculadas": n,
            "items_sin_apu": sin_apu,
            "fecha_precios": v.fecha_precios,
            "ciudad_precios_id": v.ciudad_precios_id,
            "total_costo_directo": total_cd,
        },
    )
    _commit(db)
    return s.RecalculoOut(
        version_id=v.id,
        lineas_recalculadas=n,
        insumos_sin_precio=sorted(sin_precio),
        items_sin_apu=sin_apu,
        total_costo_directo=total_cd,
    )


# --- Líneas ------------------------------------------------------------------------------
def _linea_out(ln: PresupuestoLinea, cap: EdtNodo | None) -> s.LineaOut:
    item = ln.item
    return s.LineaOut(
        id=ln.id,
        version_id=ln.version_id,
        item_id=ln.item_id,
        item_codigo=item.codigo,
        item_descripcion=item.descripcion,
        unidad_codigo=item.unidad.codigo if item.unidad else None,
        capitulo_id=cap.id if cap else None,
        capitulo_codigo=cap.codigo if cap else None,
        capitulo_descripcion=cap.descripcion if cap else None,
        cantidad=ln.cantidad,
        valor_unitario=ln.valor_unitario,
        valor_total=ln.valor_total,
        origen_unitario=ln.origen_unitario,
        orden=ln.orden,
        observacion=ln.observacion,
        num_insumos=len(ln.insumos),
        insumos_sin_precio=sorted(li.insumo_id for li in ln.insumos if li.precio_faltante),
        created_at=ln.created_at,
        updated_at=ln.updated_at,
        created_by=ln.created_by,
        updated_by=ln.updated_by,
    )


def linea_out(db: Session, ln: PresupuestoLinea) -> s.LineaOut:
    return _linea_out(ln, capitulos_de_items(db, [ln.item_id]).get(ln.item_id))


def listar_lineas(
    db: Session, version_id: int, *, capitulo_id: int | None = None, q: str | None = None
) -> list[s.LineaOut]:
    obtener_version(db, version_id)
    lineas = _lineas_con_snapshot(db, version_id)
    caps = capitulos_de_items(db, (ln.item_id for ln in lineas))
    patron = q.strip().lower() if q else None
    out: list[s.LineaOut] = []
    for ln in lineas:
        cap = caps.get(ln.item_id)
        if capitulo_id is not None and (cap is None or cap.id != capitulo_id):
            continue
        if patron and patron not in ln.item.codigo.lower() and patron not in ln.item.descripcion.lower():
            continue
        out.append(_linea_out(ln, cap))
    out.sort(key=lambda x: x.item_codigo)
    return out


def _obtener_linea(db: Session, version_id: int, linea_id: int) -> PresupuestoLinea:
    ln = db.scalar(
        select(PresupuestoLinea)
        .where(PresupuestoLinea.id == linea_id)
        .options(selectinload(PresupuestoLinea.insumos))
    )
    if ln is None or ln.version_id != version_id:
        raise NotFoundError(f"Línea {linea_id} no existe en la versión {version_id}")
    return ln


def crear_linea(db: Session, version_id: int, data: s.LineaCreate) -> PresupuestoLinea:
    v = obtener_version_para_escritura(db, version_id)
    asegurar_editable(v)
    item = db.get(EdtNodo, data.item_id)
    if item is None:
        raise NotFoundError(f"Ítem EDT {data.item_id} no existe")
    existe = db.scalar(
        select(PresupuestoLinea.id).where(
            PresupuestoLinea.version_id == v.id, PresupuestoLinea.item_id == data.item_id
        )
    )
    if existe is not None:
        raise ConflictError(f"El ítem {item.codigo} ya está en la versión", details={"linea_id": existe})
    try:
        _aplicar(db, v, [data], modo="crear", origen_manual=OrigenValor.MANUAL)
    except BusinessRuleError as exc:
        db.rollback()
        detalle = exc.details[0]["mensaje"] if isinstance(exc.details, list) and exc.details else exc.message
        raise BusinessRuleError(detalle) from exc
    _commit(db)
    ln_id = db.scalar(
        select(PresupuestoLinea.id).where(
            PresupuestoLinea.version_id == v.id, PresupuestoLinea.item_id == data.item_id
        )
    )
    return _obtener_linea(db, v.id, int(ln_id))  # type: ignore[arg-type]


def crear_lineas_lote(db: Session, version_id: int, lineas: list[s.LineaCreate]) -> s.LoteResultado:
    v = obtener_version_para_escritura(db, version_id)
    asegurar_editable(v)
    try:
        res = _aplicar(db, v, lineas, modo="crear", origen_manual=OrigenValor.MANUAL)
    except BusinessRuleError as exc:
        db.rollback()
        errores = exc.details if isinstance(exc.details, list) else [{"indice": -1, "mensaje": exc.message}]
        return s.LoteResultado(creadas=0, errores=[s.ErrorLinea(**e) for e in errores])
    _commit(db)
    return s.LoteResultado(creadas=res["creadas"], errores=[])


def actualizar_linea(db: Session, version_id: int, linea_id: int, data: s.LineaUpdate) -> PresupuestoLinea:
    v = obtener_version_para_escritura(db, version_id)
    asegurar_editable(v)
    ln = _obtener_linea(db, version_id, linea_id)
    cambios = data.model_dump(exclude_unset=True)
    if cambios.get("cantidad") is not None:
        ln.cantidad = cambios["cantidad"]
    if "observacion" in cambios:
        ln.observacion = cambios["observacion"]
    if cambios.get("orden") is not None:
        ln.orden = cambios["orden"]
    if cambios.get("valor_unitario") is not None:
        _valor_manual(db, ln, cambios["valor_unitario"], OrigenValor.MANUAL)
    else:
        ln.valor_total = valor_total_linea(ln.cantidad, ln.valor_unitario)
    _commit(db)
    return _obtener_linea(db, version_id, linea_id)


def eliminar_linea(db: Session, version_id: int, linea_id: int) -> None:
    v = obtener_version_para_escritura(db, version_id)
    asegurar_editable(v)
    db.delete(_obtener_linea(db, version_id, linea_id))
    _commit(db)


def listar_insumos_linea(db: Session, version_id: int, linea_id: int) -> list[s.LineaInsumoOut]:
    ln = _obtener_linea(db, version_id, linea_id)
    out: list[s.LineaInsumoOut] = []
    for li in sorted(ln.insumos, key=lambda x: x.insumo.codigo):
        ins = li.insumo
        cant = cantidad_exacta_insumo(ln.cantidad, li.cantidad_unitaria, li.desperdicio_pct)
        out.append(
            s.LineaInsumoOut(
                insumo_id=li.insumo_id,
                insumo_codigo=ins.codigo,
                insumo_descripcion=ins.descripcion,
                unidad_codigo=ins.unidad.codigo if ins.unidad else None,
                tipo=ins.tipo,
                cantidad_unitaria=li.cantidad_unitaria,
                desperdicio_pct=li.desperdicio_pct,
                precio_unitario=li.precio_unitario,
                valor_unitario=li.valor_unitario,
                precio_faltante=li.precio_faltante,
                cantidad_total=q4(cant),
                valor_total=valor_total_insumo(cant, li.precio_unitario),
            )
        )
    return out
