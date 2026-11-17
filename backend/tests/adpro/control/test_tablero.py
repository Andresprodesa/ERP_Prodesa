"""Tablero presupuesto vs comprometido vs ejecutado (§5.4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core.errors import BusinessRuleError
from app.modules.adpro.control import service
from app.modules.adpro.control.schemas import (
    CompromisoCreate,
    CompromisoLineaIn,
    EjecucionLote,
    EjecucionRegistroIn,
)
from app.modules.adpro.enums import EstadoVersion, TipoCompromiso, TipoVersion
from app.modules.adpro.models import Presupuesto
from tests.adpro.control.conftest import Escenario, agregar_linea, nueva_version

D = Decimal


@pytest.fixture()
def con_movimientos(db, escenario: Escenario) -> Escenario:
    e = escenario

    def comp(numero: str, lineas: list[tuple[int, str, str]]) -> int:
        return service.crear_compromiso(
            db,
            CompromisoCreate(
                presupuesto_id=e.presupuesto.id,
                tipo=TipoCompromiso.ORDEN_COMPRA,
                numero=numero,
                fecha=date(2026, 9, 1),
                tercero="Proveedor Demo S.A.S.",
                lineas=[
                    CompromisoLineaIn(item_id=i, cantidad=D(q), valor_unitario=D(v)) for i, q, v in lineas
                ],
            ),
        ).id

    comp("OC-1", [(e.item_a.id, "60", "12000"), (e.item_c.id, "1", "650000")])
    anulado = comp("OC-2", [(e.item_b.id, "1", "50000")])
    service.anular_compromiso(db, anulado, "Prueba")

    def ejec(periodo: str, regs: list[tuple[int, str, str]]) -> None:
        service.guardar_ejecucion(
            db,
            EjecucionLote(
                presupuesto_id=e.presupuesto.id,
                periodo=periodo,
                registros=[
                    EjecucionRegistroIn(item_id=i, valor_ejecutado=D(v), avance_fisico_pct=D(a))
                    for i, v, a in regs
                ],
            ),
        )

    ejec("2026-09", [(e.item_a.id, "300000", "0.25"), (e.item_c.id, "200000", "0.3")])
    ejec("2026-10", [(e.item_a.id, "400000", "0.5")])
    return e


def test_tablero_por_capitulo(db, con_movimientos: Escenario) -> None:
    e = con_movimientos
    t = service.tablero(db, e.presupuesto.id)
    assert t.version.id == e.v_control.id  # CONTROL aprobada por defecto
    assert t.periodo_hasta == "2026-10"
    caps = {f.codigo: f for f in t.capitulos}
    c1, c2 = caps["01"], caps["02"]
    assert (c1.presupuestado, c1.comprometido, c1.ejecutado) == (D("1260000"), D("720000"), D("700000"))
    assert c1.por_comprometer == D("540000") and c1.saldo == D("560000")
    assert c1.pct_comprometido == D("0.571429") and c1.pct_ejecutado == D("0.555556")
    # (0.5*1.210.000 + 0*50.000) / 1.260.000
    assert c1.avance_fisico_pct == D("0.480159")
    assert c1.id == e.cap1.id
    assert (c2.presupuestado, c2.comprometido, c2.ejecutado) == (D("600000"), D("650000"), D("200000"))
    assert c2.por_comprometer == D("-50000") and c2.avance_fisico_pct == D("0.300000")
    tot = t.totales
    assert (tot.presupuestado, tot.comprometido, tot.ejecutado) == (D("1860000"), D("1370000"), D("900000"))
    assert tot.avance_fisico_pct == D("0.422043") and tot.id is None
    assert [(s.periodo, s.ejecutado, s.ejecutado_acumulado) for s in t.serie_mensual] == [
        ("2026-09", D("500000"), D("500000")),
        ("2026-10", D("400000"), D("900000")),
    ]


def test_tablero_periodo_hasta(db, con_movimientos: Escenario) -> None:
    t = service.tablero(db, con_movimientos.presupuesto.id, periodo_hasta="2026-09")
    assert t.totales.ejecutado == D("500000") and len(t.serie_mensual) == 1
    items = {
        f.codigo: f
        for f in service.tablero_items(db, con_movimientos.presupuesto.id, periodo_hasta="2026-09")
    }
    assert items["01.01.001.0001"].avance_fisico_pct == D("0.25")


def test_tablero_items_y_filtro_capitulo(db, con_movimientos: Escenario) -> None:
    e = con_movimientos
    filas = service.tablero_items(db, e.presupuesto.id)
    assert [f.codigo for f in filas] == ["01.01.001.0001", "01.01.001.0002", "02.01.001.0001"]
    a = filas[0]
    assert a.id == e.item_a.id and a.presupuestado == D("1210000") and a.avance_fisico_pct == D("0.5")
    b = filas[1]
    assert b.comprometido == 0  # el compromiso anulado no suma
    solo2 = service.tablero_items(db, e.presupuesto.id, capitulo_id=e.cap2.id)
    assert [f.codigo for f in solo2] == ["02.01.001.0001"]


def test_resolucion_de_version(db, escenario: Escenario) -> None:
    e = escenario
    # version explícita (puede ser cualquier estado) del mismo presupuesto
    assert service.tablero(db, e.presupuesto.id, version_id=e.v_fiv.id).version.id == e.v_fiv.id
    otro = Presupuesto(proyecto_id=e.proyecto.id, codigo="PPTO-2", nombre="Otro demo")
    db.add(otro)
    db.flush()
    with pytest.raises(BusinessRuleError):
        service.tablero(db, otro.id, version_id=e.v_fiv.id)  # no pertenece
    with pytest.raises(BusinessRuleError):
        service.tablero(db, otro.id)  # sin versiones aprobadas
    # sin CONTROL aprobada -> última APROBADA
    v1 = nueva_version(db, otro, 1, TipoVersion.FIC)
    agregar_linea(db, v1, e.item_a, "1")
    v1.estado = EstadoVersion.APROBADO
    nueva_version(db, otro, 2, TipoVersion.CONTROL)  # BORRADOR: se ignora
    db.commit()
    t = service.tablero(db, otro.id)
    assert t.version.id == v1.id and t.totales.presupuestado == D("12100")
    assert t.periodo_hasta is None and t.serie_mensual == []
    assert t.totales.avance_fisico_pct == 0


def test_endpoints_tablero(client_as, con_movimientos: Escenario) -> None:
    c = client_as("consulta")
    pid = con_movimientos.presupuesto.id
    r = c.get("/api/adpro/control/tablero", params={"presupuesto_id": pid})
    assert r.status_code == 200, r.text
    assert D(r.json()["totales"]["presupuestado"]) == D("1860000")
    assert r.json()["version"]["tipo"] == "CONTROL"
    r = c.get(
        "/api/adpro/control/tablero/items",
        params={"presupuesto_id": pid, "capitulo_id": con_movimientos.cap1.id},
    )
    assert r.status_code == 200 and len(r.json()) == 2
    assert (
        c.get(
            "/api/adpro/control/tablero", params={"presupuesto_id": pid, "periodo_hasta": "2026-9"}
        ).status_code
        == 422
    )
    assert c.get("/api/adpro/control/tablero", params={"presupuesto_id": 9999}).status_code == 404
