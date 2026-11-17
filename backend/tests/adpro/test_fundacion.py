"""Tests de la fundación ADPRO: cálculos puros, valorización con precio vigente y restricciones."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.adpro import calculos as c
from app.modules.adpro.enums import NivelEdt, TipoInsumo
from app.modules.adpro.models import (
    Apu,
    ApuInsumo,
    Ciudad,
    EdtNodo,
    Insumo,
    ListaPrecios,
    PrecioInsumo,
    Unidad,
)
from app.modules.adpro.valorizacion import precio_vigente, valorizar_apu

D = Decimal


def test_redondeo_half_up() -> None:
    assert c.redondear_pesos(D("10.5")) == D("11")
    assert c.redondear_pesos(D("-10.5")) == D("-11")
    assert c.redondear_pesos(D("10.4999")) == D("10")
    assert c.q4(D("0.00005")) == D("0.0001")


def test_valor_unitario_apu() -> None:
    # 2 * 1.05 * 1000 + 0.5 * 1 * 20000 = 2100 + 10000
    assert c.valor_unitario_apu([(D("2"), D("0.05"), D("1000")), (D("0.5"), D("0"), D("20000"))]) == D(
        "12100.0000"
    )


def test_aiu_e_iva() -> None:
    r = c.calcular_aiu(D("1000000"), D("0.08"), D("0.02"), D("0.05"), D("0.19"))
    assert (r.administracion, r.imprevistos, r.utilidad) == (D("80000"), D("20000"), D("50000"))
    assert r.iva_utilidad == D("9500")
    assert r.total_aiu == D("150000")
    assert r.total == D("1159500")


def test_linea_explosion_variacion_periodo() -> None:
    assert c.valor_total_linea(D("3.333"), D("1000.4")) == D("3334")
    assert c.cantidad_total_insumo(D("100"), D("0.25"), D("0.1")) == D("27.5000")
    assert c.variacion_pct(D("100"), D("110")) == D("0.100000")
    assert c.variacion_pct(D("0"), D("10")) is None
    assert c.es_periodo_valido("2026-11") and not c.es_periodo_valido("2026-13")


def test_participacion_pct() -> None:
    assert c.participacion_pct(D("6074746"), D("6355248")) == D("0.955863")
    assert c.participacion_pct(D("1"), D("3")) == D("0.333333")
    assert c.participacion_pct(D("5"), D("0")) is None
    assert c.participacion_pct(0, 10) == D("0.000000")


def test_nivel_edt_jerarquia() -> None:
    assert NivelEdt.CAPITULO.padre_requerido is None
    assert NivelEdt.ITEM.padre_requerido is NivelEdt.GRUPO
    assert NivelEdt.GRUPO.profundidad == 3


@pytest.fixture()
def escenario(db):  # type: ignore[no-untyped-def]
    un = Unidad(codigo="M2", nombre="Metro cuadrado")
    kg = Unidad(codigo="KG", nombre="Kilogramo")
    bog = Ciudad(codigo="BOG", nombre="Bogotá D.C.")
    db.add_all([un, kg, bog])
    db.flush()
    cem = Insumo(codigo="MAT-001", descripcion="Cemento gris (demo)", unidad_id=kg.id, tipo=TipoInsumo.MAT)
    mo = Insumo(codigo="MO-001", descripcion="Cuadrilla (demo)", unidad_id=un.id, tipo=TipoInsumo.MO)
    db.add_all([cem, mo])
    cap = EdtNodo(nivel=NivelEdt.CAPITULO, codigo="01", descripcion="Preliminares")
    db.add(cap)
    db.flush()
    det = EdtNodo(nivel=NivelEdt.DETALLE, codigo="01.01", descripcion="Det", parent_id=cap.id)
    db.add(det)
    db.flush()
    gru = EdtNodo(nivel=NivelEdt.GRUPO, codigo="01.01.001", descripcion="Gru", parent_id=det.id)
    db.add(gru)
    db.flush()
    item = EdtNodo(
        nivel=NivelEdt.ITEM, codigo="01.01.001.0001", descripcion="Ítem", parent_id=gru.id, unidad_id=un.id
    )
    db.add(item)
    db.flush()
    l1 = ListaPrecios(codigo="BOG-2026-01", nombre="L1", ciudad_id=bog.id, fecha_desde=date(2026, 1, 1))
    l2 = ListaPrecios(codigo="BOG-2026-07", nombre="L2", ciudad_id=bog.id, fecha_desde=date(2026, 7, 1))
    db.add_all([l1, l2])
    db.flush()
    db.add_all(
        [
            PrecioInsumo(lista_id=l1.id, insumo_id=cem.id, precio=D("1000")),
            PrecioInsumo(lista_id=l1.id, insumo_id=mo.id, precio=D("20000")),
            PrecioInsumo(lista_id=l2.id, insumo_id=cem.id, precio=D("1200")),  # MO no está en L2
        ]
    )
    apu = Apu(item_id=item.id, descripcion="APU demo")
    apu.insumos = [
        ApuInsumo(insumo_id=cem.id, cantidad=D("2"), desperdicio_pct=D("0.05"), orden=1),
        ApuInsumo(insumo_id=mo.id, cantidad=D("0.5"), desperdicio_pct=D("0"), orden=2),
    ]
    db.add(apu)
    db.commit()
    return {"bog": bog, "cem": cem, "mo": mo, "apu": apu, "item": item, "un": un}


def test_precio_vigente_por_fecha(db, escenario) -> None:  # type: ignore[no-untyped-def]
    bog, cem, mo = escenario["bog"], escenario["cem"], escenario["mo"]
    assert precio_vigente(db, cem.id, bog.id, date(2025, 12, 31)) is None
    assert precio_vigente(db, cem.id, bog.id, date(2026, 3, 1)).precio == D("1000")
    assert precio_vigente(db, cem.id, bog.id, date(2026, 7, 1)).precio == D("1200")
    # MO no está en la lista de julio: se usa la anterior
    assert precio_vigente(db, mo.id, bog.id, date(2026, 8, 1)).precio == D("20000")


def test_valorizar_apu(db, escenario) -> None:  # type: ignore[no-untyped-def]
    apu = db.scalar(select(Apu).where(Apu.id == escenario["apu"].id))
    v = valorizar_apu(db, apu, escenario["bog"].id, date(2026, 8, 1))
    # 2 * 1.05 * 1200 + 0.5 * 20000 = 2520 + 10000
    assert v.valor_unitario == D("12520.0000")
    assert v.insumos_sin_precio == []
    v0 = valorizar_apu(db, apu, escenario["bog"].id, date(2025, 1, 1))
    assert v0.valor_unitario == D("0") and len(v0.insumos_sin_precio) == 2


def test_restriccion_item_requiere_unidad(db, escenario) -> None:  # type: ignore[no-untyped-def]
    db.add(
        EdtNodo(nivel=NivelEdt.ITEM, codigo="99", descripcion="Sin unidad", parent_id=escenario["item"].id)
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_unico_precio_por_lista_e_insumo(db, escenario) -> None:  # type: ignore[no-untyped-def]
    lista = db.scalar(select(ListaPrecios).where(ListaPrecios.codigo == "BOG-2026-01"))
    db.add(PrecioInsumo(lista_id=lista.id, insumo_id=escenario["cem"].id, precio=D("1")))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
