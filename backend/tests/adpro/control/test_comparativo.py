"""Comparativo entre versiones (§5.1): nivel ítem, insumo y capítulo."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import NotFoundError
from app.modules.adpro.control import service
from tests.adpro.control.conftest import Escenario

D = Decimal


def _por_codigo(out):  # type: ignore[no-untyped-def]
    return {f.codigo: f for f in out.filas}


def test_comparativo_por_item_estados_y_cifras(db, escenario: Escenario) -> None:
    out = service.comparar_versiones(db, escenario.v_fic.id, escenario.v_fiv.id, "item")
    f = _por_codigo(out)
    assert set(f) == {"01.01.001.0001", "01.01.001.0002", "02.01.001.0001", "02.01.001.0002"}

    a = f["01.01.001.0001"]
    assert a.estado == "IGUAL" and a.impacto == 0 and a.variacion_pct == 0
    assert a.unitario_base == D("12100") and a.capitulo_codigo == "01" and a.unidad_codigo == "M2"

    b = f["01.01.001.0002"]
    assert b.estado == "MODIFICADO"
    assert (b.cantidad_base, b.cantidad_comparada, b.diferencia_cantidad) == (D("10"), D("12"), D("2"))
    assert b.diferencia_unitaria == 0
    assert (b.total_base, b.total_comparado, b.impacto) == (D("50000"), D("60000"), D("10000"))
    assert b.variacion_pct == D("0.200000")

    c = f["02.01.001.0001"]
    assert c.estado == "ELIMINADO" and c.total_comparado == 0 and c.impacto == D("-600000")
    assert c.variacion_pct == D("-1.000000")

    d = f["02.01.001.0002"]
    assert d.estado == "NUEVO" and d.total_base == 0 and d.impacto == D("5000")
    assert d.variacion_pct is None  # base 0

    assert out.totales.total_base == D("1860000")
    assert out.totales.total_comparado == D("1275000")
    assert out.totales.impacto == D("-585000")
    assert out.version_base.tipo.value == "FIC" and out.version_comparada.tipo.value == "FIV"
    assert [x.codigo for x in out.filas] == sorted(f)


def test_comparativo_diferencia_unitaria(db, escenario: Escenario) -> None:
    from app.modules.adpro.enums import TipoVersion
    from tests.adpro.control.conftest import agregar_linea, nueva_version

    v = nueva_version(db, escenario.presupuesto, 9, TipoVersion.OTRO)
    agregar_linea(db, v, escenario.item_c, "2", "330000")
    db.commit()
    out = service.comparar_versiones(db, escenario.v_fic.id, v.id, "item")
    c = _por_codigo(out)["02.01.001.0001"]
    assert c.estado == "MODIFICADO"
    assert c.diferencia_unitaria == D("30000") and c.impacto == D("60000")
    assert c.variacion_pct == D("0.100000")


def test_comparativo_por_insumo_usa_snapshot(db, escenario: Escenario) -> None:
    out = service.comparar_versiones(db, escenario.v_fic.id, escenario.v_fiv.id, "insumo")
    f = _por_codigo(out)
    assert set(f) == {"MAT-001", "MAT-002", "MO-001"}
    cem = f["MAT-001"]
    assert cem.estado == "IGUAL" and cem.cantidad_base == D("210.0000") and cem.total_base == D("210000")
    assert cem.unitario_base == D("1000.0000") and cem.tipo.value == "MAT" and cem.unidad_codigo == "KG"
    assert f["MO-001"].total_base == D("1000000") and f["MO-001"].cantidad_base == D("50.0000")
    blq = f["MAT-002"]
    assert blq.estado == "MODIFICADO" and blq.diferencia_cantidad == D("2.0000") and blq.impacto == D("10000")
    # Las líneas manuales no tienen desglose: no aparecen por insumo.
    assert out.totales.total_base == D("1260000") and out.totales.total_comparado == D("1270000")


def test_comparativo_por_capitulo(db, escenario: Escenario) -> None:
    out = service.comparar_versiones(db, escenario.v_fic.id, escenario.v_fiv.id, "capitulo")
    f = _por_codigo(out)
    assert f["01"].total_base == D("1260000") and f["01"].total_comparado == D("1270000")
    assert f["01"].estado == "MODIFICADO" and f["01"].cantidad_base is None
    assert f["02"].total_base == D("600000") and f["02"].total_comparado == D("5000")
    assert f["02"].clave_id == escenario.cap2.id
    assert out.totales.impacto == D("-585000")


def test_comparativo_version_inexistente(db, escenario: Escenario) -> None:
    with pytest.raises(NotFoundError):
        service.comparar_versiones(db, escenario.v_fic.id, 99999, "item")


def test_endpoint_comparativo(client_as, escenario: Escenario) -> None:
    c = client_as("consulta")
    r = c.get(
        "/api/adpro/control/comparativo",
        params={"version_base_id": escenario.v_fic.id, "version_comparada_id": escenario.v_fiv.id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nivel"] == "item"
    assert D(body["totales"]["total_base"]) == D("1860000")
    assert {f["estado"] for f in body["filas"]} == {"IGUAL", "MODIFICADO", "NUEVO", "ELIMINADO"}

    r = c.get(
        "/api/adpro/control/comparativo",
        params={
            "version_base_id": escenario.v_fic.id,
            "version_comparada_id": escenario.v_fiv.id,
            "nivel": "xx",
        },
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"

    r = c.get("/api/adpro/control/comparativo", params={"version_base_id": 999, "version_comparada_id": 998})
    assert r.status_code == 404


def test_endpoint_comparativo_requiere_auth(client, escenario: Escenario) -> None:
    r = client.get(
        "/api/adpro/control/comparativo",
        params={"version_base_id": escenario.v_fic.id, "version_comparada_id": escenario.v_fiv.id},
    )
    assert r.status_code == 401
