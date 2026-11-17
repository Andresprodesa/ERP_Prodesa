"""El seed de desarrollo + demo corre sobre una BD vacía, es idempotente y sus cifras cuadran."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.models import AuditLog, Usuario
from app.modules.adpro import seed_demo
from app.modules.adpro.calculos import calcular_aiu, valor_total_linea
from app.modules.adpro.enums import EstadoCompromiso, EstadoVersion, NivelEdt, OrigenValor, TipoVersion
from app.modules.adpro.models import (
    Apu,
    Compromiso,
    EdtNodo,
    Ejecucion,
    Insumo,
    ListaPrecios,
    PresupuestoLinea,
    PresupuestoVersion,
    Proyecto,
)
from app.seed import run


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture()
def sembrada(db: Session) -> Session:
    res = run(db)
    assert res["demo"] > 0
    return db


def test_seed_sobre_bd_vacia_crea_todo(sembrada: Session) -> None:
    db = sembrada
    assert _count(db, Usuario) == 4
    assert _count(db, Insumo) >= 60
    assert _count(db, ListaPrecios) == 4
    assert _count(db, Proyecto) == 2
    capitulos = db.scalars(select(EdtNodo).where(EdtNodo.nivel == NivelEdt.CAPITULO)).all()
    assert len(capitulos) == 8
    items = _count(db, Apu)
    assert items >= 40
    assert items == db.scalar(select(func.count()).where(EdtNodo.nivel == NivelEdt.ITEM))
    assert _count(db, Ejecucion) > 0
    periodos = set(db.scalars(select(Ejecucion.periodo)))
    assert periodos == {"2026-08", "2026-09", "2026-10"}


def test_seed_es_idempotente(sembrada: Session) -> None:
    antes = _count(sembrada, Insumo), _count(sembrada, PresupuestoLinea)
    res = run(sembrada)
    assert res["demo"] == 0
    assert res["usuarios"] == 0
    assert (_count(sembrada, Insumo), _count(sembrada, PresupuestoLinea)) == antes


def test_version_base_aprobada_cuadra_con_calculos(sembrada: Session) -> None:
    db = sembrada
    base = db.scalar(
        select(PresupuestoVersion).where(
            PresupuestoVersion.tipo == TipoVersion.BASE, PresupuestoVersion.estado == EstadoVersion.APROBADO
        )
    )
    assert base is not None
    cd = Decimal("0")
    for ln in base.lineas:
        assert ln.origen_unitario == OrigenValor.APU
        assert ln.insumos, "las líneas APU guardan snapshot de insumos"
        assert ln.valor_unitario == sum((i.valor_unitario for i in ln.insumos), Decimal("0"))
        assert ln.valor_total == valor_total_linea(ln.cantidad, ln.valor_unitario)
        assert not any(i.precio_faltante for i in ln.insumos)
        cd += ln.valor_total
    aiu = calcular_aiu(
        cd, base.administracion_pct, base.imprevistos_pct, base.utilidad_pct, base.iva_utilidad_pct
    )
    assert base.total_costo_directo == aiu.costo_directo
    assert base.total_presupuesto == aiu.total
    assert base.aprobado_at is not None
    # Orden de magnitud plausible (EDT demo parcial, 240 viviendas): miles de millones de COP
    assert Decimal("5e9") < cd < Decimal("60e9")
    assert db.scalar(select(func.count()).where(AuditLog.accion == "APROBAR")) == 1


def test_version_control_borrador_con_cambios(sembrada: Session) -> None:
    db = sembrada
    control = db.scalar(select(PresupuestoVersion).where(PresupuestoVersion.tipo == TipoVersion.CONTROL))
    assert control is not None
    assert control.estado == EstadoVersion.BORRADOR
    assert control.version_origen_id is not None
    assert control.total_costo_directo is None
    base = db.get(PresupuestoVersion, control.version_origen_id)
    items_base = {ln.item_id for ln in base.lineas}
    items_control = {ln.item_id for ln in control.lineas}
    assert items_control - items_base, "hay al menos un ítem NUEVO"
    assert items_base - items_control, "hay al menos un ítem ELIMINADO"
    manuales = [ln for ln in control.lineas if ln.origen_unitario == OrigenValor.MANUAL]
    assert len(manuales) == 1 and not manuales[0].insumos
    assert manuales[0].item.descripcion == seed_demo.ITEM_SOLO_CONTROL
    # Precios de julio: el acero subió, así que el unitario de control es mayor
    unit_base = {ln.item_id: ln.valor_unitario for ln in base.lineas}
    assert any(ln.valor_unitario > unit_base[ln.item_id] for ln in control.lineas if ln.item_id in unit_base)


def test_compromisos_y_ejecucion(sembrada: Session) -> None:
    db = sembrada
    comps = db.scalars(select(Compromiso)).all()
    assert len(comps) >= 5
    assert any(c.estado == EstadoCompromiso.ANULADO for c in comps)
    for c in comps:
        assert c.valor_total == sum((ln.valor_total for ln in c.lineas), Decimal("0"))
        assert "S.A.S." in c.tercero or "Ltda." in c.tercero
    for e in db.scalars(select(Ejecucion)):
        assert Decimal("0") <= e.avance_fisico_pct <= Decimal("1")
        assert e.valor_ejecutado > 0
