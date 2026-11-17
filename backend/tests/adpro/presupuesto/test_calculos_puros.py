"""Funciones de cálculo PURAS del presupuesto (sin BD), con ejemplos calculados a mano."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.modules.adpro.calculos import valor_total_linea
from app.modules.adpro.presupuesto.service import (
    FilaSnapshot,
    explotar_insumos,
    participacion,
    totales_por_capitulo,
    totales_version,
)

D = Decimal


def test_redondeo_linea_half_up() -> None:
    assert valor_total_linea(D("1"), D("2500.5")) == D("2501")  # banker's daría 2500
    assert valor_total_linea(D("3"), D("0.5")) == D("2")  # 1.5 -> 2
    assert valor_total_linea(D("12.35"), D("393416.6640")) == D("4858696")  # 4858695.8004
    assert valor_total_linea(D("3.3"), D("85000.5")) == D("280502")  # 280501.65


def test_totales_version_aiu_e_iva_sobre_utilidad() -> None:
    v = SimpleNamespace(
        administracion_pct=D("0.08"),
        imprevistos_pct=D("0.02"),
        utilidad_pct=D("0.05"),
        iva_utilidad_pct=D("0.19"),
    )
    r = totales_version([D("1216050"), D("4858696"), D("280502")], v)  # type: ignore[arg-type]
    assert r.costo_directo == D("6355248")
    assert r.administracion == D("508420")  # 508419.84
    assert r.imprevistos == D("127105")  # 127104.96
    assert r.utilidad == D("317762")  # 317762.40
    assert r.iva_utilidad == D("60375")  # 317762 · 0.19 = 60374.78 (IVA sobre la utilidad YA redondeada)
    assert r.total_aiu == D("953287")
    assert r.total == D("7368910")


def test_totales_version_sin_aiu() -> None:
    v = SimpleNamespace(
        administracion_pct=D("0"), imprevistos_pct=D("0"), utilidad_pct=D("0"), iva_utilidad_pct=D("0.19")
    )
    r = totales_version([], v)  # type: ignore[arg-type]
    assert (r.costo_directo, r.total) == (D("0"), D("0"))


def test_participacion() -> None:
    assert participacion(D("6074746"), D("6355248")) == D("0.955863")
    assert participacion(D("5"), D("0")) == D("0")


def test_totales_por_capitulo() -> None:
    r = totales_por_capitulo([("01", D("100")), ("02", D("50")), ("01", D("25"))])
    assert (r["01"].valor, r["01"].num_lineas) == (D("125"), 2)
    assert (r["02"].valor, r["02"].num_lineas) == (D("50"), 1)


def test_explosion_con_desperdicio_y_redondeo() -> None:
    filas = [
        # Muro 100.5 M2: cemento 2 KG +5 % -> 211.05 KG ; MO 0.5 HR -> 50.25 HR
        FilaSnapshot(1, D("100.5"), D("2"), D("0.05"), D("1000")),
        FilaSnapshot(2, D("100.5"), D("0.5"), D("0"), D("20000")),
        # Concreto 12.35 M3: cemento 350 +3 % -> 4452.175 ; arena 0.55 +10 % -> 7.47175 (se muestra
        # 7.4718; se valoriza con la exacta: 7.47175 · 50000 = 373587.5 -> 373588)
        FilaSnapshot(1, D("12.35"), D("350"), D("0.03"), D("1000")),
        FilaSnapshot(3, D("12.35"), D("0.55"), D("0.10"), D("50000")),
        # equipo 0.333333 -> 4.11666255 (muestra 4.1167) ; 4.11666255 · 8000 = 32933.30 -> 32933
        FilaSnapshot(4, D("12.35"), D("0.333333"), D("0"), D("8000")),
    ]
    r = explotar_insumos(filas)
    assert (r[1].cantidad_total, r[1].valor_total) == (D("4663.225"), D("4663225"))
    assert r[1].precio_unitario == D("1000.0000")
    assert (r[2].cantidad_total, r[2].valor_total) == (D("50.25"), D("1005000"))
    assert (r[3].cantidad_total, r[3].valor_total) == (D("7.4718"), D("373588"))
    assert (r[4].cantidad_total, r[4].valor_total) == (D("4.1167"), D("32933"))
    assert r[4].precio_unitario == D("7999.8543")  # 32933 / 4.1167 (precio medio = valor/cantidad, §4.4)


def test_explosion_vacia_y_cantidad_cero() -> None:
    assert explotar_insumos([]) == {}
    r = explotar_insumos([FilaSnapshot(9, D("0"), D("3"), D("0.1"), D("100"))])
    assert r[9].cantidad_total == 0 and r[9].precio_unitario == 0
