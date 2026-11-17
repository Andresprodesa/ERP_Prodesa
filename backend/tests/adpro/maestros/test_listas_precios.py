"""Listas de precios con vigencia, carga de precios, histórico y precio vigente."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import AuditLog
from app.modules.adpro.maestros import service

from .conftest import API

D = Decimal


def _cargar(api: TestClient, lista_id: int, precios: list[dict]) -> dict:
    r = api.put(f"{API}/listas-precios/{lista_id}/precios", json={"precios": precios})
    assert r.status_code == 200, r.text
    return r.json()


def test_crear_lista_y_duplicados(api: TestClient, crear_lista, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    lista = crear_lista("bog-2026-01", "2026-01-01")
    assert lista["codigo"] == "BOG-2026-01" and lista["ciudad_codigo"] == "BOG"
    assert lista["num_precios"] == 0 and lista["activo"] is True

    # misma ciudad + fecha -> 409
    r = api.post(
        f"{API}/listas-precios",
        json={"codigo": "OTRA", "nombre": "x", "ciudad_id": ciudad_id("BOG"), "fecha_desde": "2026-01-01"},
    )
    assert r.status_code == 409 and "BOG" in r.json()["error"]["message"]
    # mismo código -> 409
    r = api.post(
        f"{API}/listas-precios",
        json={
            "codigo": "BOG-2026-01",
            "nombre": "x",
            "ciudad_id": ciudad_id("MDE"),
            "fecha_desde": "2026-01-01",
        },
    )
    assert r.status_code == 409
    # ciudad inexistente -> 422
    r = api.post(
        f"{API}/listas-precios",
        json={"codigo": "NUEVA", "nombre": "x", "ciudad_id": 9999, "fecha_desde": "2026-01-01"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    # misma fecha en otra ciudad sí
    crear_lista("MDE-2026-01", "2026-01-01", ciudad="MDE")


def test_cargar_precios_upsert_y_listado(api: TestClient, crear_lista, crear_insumo) -> None:  # type: ignore[no-untyped-def]
    a = crear_insumo("MAT-001", "Cemento (demo)", "BTO", "MAT")
    b = crear_insumo("MO-001", "Cuadrilla (demo)", "DIA", "MO")
    lista = crear_lista("BOG-2026-01", "2026-01-01")

    res = _cargar(
        api, lista["id"], [{"insumo_id": a["id"], "precio": "32000.50", "fuente": "Cotización demo"}]
    )
    assert res == {"creados": 1, "actualizados": 0}
    res = _cargar(
        api,
        lista["id"],
        [{"insumo_id": a["id"], "precio": 33000}, {"insumo_id": b["id"], "precio": "150000"}],
    )
    assert res == {"creados": 1, "actualizados": 1}

    page = api.get(f"{API}/listas-precios/{lista['id']}/precios").json()
    assert page["total"] == 2
    primero = page["items"][0]
    assert primero["insumo_codigo"] == "MAT-001" and D(primero["precio"]) == D("33000")
    assert primero["fuente"] == "Cotización demo"  # no se borra si no se envía
    assert primero["unidad_codigo"] == "BTO" and primero["tipo"] == "MAT"
    assert isinstance(primero["precio"], str)

    assert api.get(f"{API}/listas-precios/{lista['id']}/precios", params={"tipo": "MO"}).json()["total"] == 1
    assert api.get(f"{API}/listas-precios/{lista['id']}/precios", params={"q": "cemen"}).json()["total"] == 1
    page = api.get(f"{API}/listas-precios/{lista['id']}/precios", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and [p["insumo_codigo"] for p in page["items"]] == ["MO-001"]
    assert api.get(f"{API}/listas-precios/{lista['id']}").json()["num_precios"] == 2


def test_cargar_precios_validaciones(api: TestClient, crear_lista, crear_insumo) -> None:  # type: ignore[no-untyped-def]
    a = crear_insumo("MAT-001")
    lista = crear_lista("L1", "2026-01-01")
    url = f"{API}/listas-precios/{lista['id']}/precios"
    assert api.put(url, json={"precios": [{"insumo_id": a["id"], "precio": "-1"}]}).status_code == 422
    assert api.put(url, json={"precios": [{"insumo_id": a["id"], "precio": "1.12345"}]}).status_code == 422
    assert api.put(url, json={"precios": []}).status_code == 422
    r = api.put(
        url, json={"precios": [{"insumo_id": a["id"], "precio": 1}, {"insumo_id": a["id"], "precio": 2}]}
    )
    assert r.status_code == 422 and "repetidos" in str(r.json()["error"]["details"])
    # todo o nada: un insumo inexistente aborta la carga completa
    r = api.put(
        url, json={"precios": [{"insumo_id": a["id"], "precio": 1}, {"insumo_id": 9999, "precio": 2}]}
    )
    assert r.status_code == 422 and r.json()["error"]["details"]["insumos_inexistentes"] == [9999]
    assert api.get(url).json()["total"] == 0
    assert (
        api.put(
            f"{API}/listas-precios/9999/precios", json={"precios": [{"insumo_id": a["id"], "precio": 1}]}
        ).status_code
        == 404
    )


def test_eliminar_precio(api: TestClient, crear_lista, crear_insumo) -> None:  # type: ignore[no-untyped-def]
    a = crear_insumo("MAT-001")
    lista = crear_lista("L1", "2026-01-01")
    _cargar(api, lista["id"], [{"insumo_id": a["id"], "precio": 100}])
    r = api.delete(f"{API}/listas-precios/{lista['id']}/precios/{a['id']}")
    assert r.status_code == 204 and r.content == b""
    assert api.delete(f"{API}/listas-precios/{lista['id']}/precios/{a['id']}").status_code == 404


def test_copiar_lista_y_actualizar(api: TestClient, crear_lista, crear_insumo, db: Session) -> None:  # type: ignore[no-untyped-def]
    a = crear_insumo("MAT-001")
    b = crear_insumo("MAT-002")
    l1 = crear_lista("L1", "2026-01-01")
    _cargar(api, l1["id"], [{"insumo_id": a["id"], "precio": 100}, {"insumo_id": b["id"], "precio": 200}])
    l2 = crear_lista("L2", "2026-07-01", copiar_de_lista_id=l1["id"], observaciones="Ajuste semestral")
    assert l2["num_precios"] == 2 and l2["observaciones"] == "Ajuste semestral"

    r = api.post(
        f"{API}/listas-precios",
        json={
            "codigo": "L3",
            "nombre": "x",
            "ciudad_id": l1["ciudad_id"],
            "fecha_desde": "2027-01-01",
            "copiar_de_lista_id": 999,
        },
    )
    assert r.status_code == 422

    r = api.put(f"{API}/listas-precios/{l2['id']}", json={"nombre": "Lista julio", "activo": False})
    assert r.status_code == 200 and r.json()["nombre"] == "Lista julio" and r.json()["activo"] is False
    # ciudad / fecha inmutables
    assert api.put(f"{API}/listas-precios/{l2['id']}", json={"fecha_desde": "2026-08-01"}).status_code == 422

    acciones = db.scalars(select(AuditLog.accion).where(AuditLog.entidad == "lista_precios")).all()
    assert acciones.count("CREAR") == 2 and "ACTUALIZAR" in acciones


def test_listar_listas_orden_y_filtros(api: TestClient, crear_lista, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    crear_lista("B1", "2026-01-01")
    crear_lista("B2", "2026-07-01")
    crear_lista("M1", "2026-03-01", ciudad="MDE")
    codigos = [x["codigo"] for x in api.get(f"{API}/listas-precios").json()]
    assert codigos == ["B2", "B1", "M1"]  # ciudad BOG < MDE, fecha desc
    assert [
        x["codigo"] for x in api.get(f"{API}/listas-precios", params={"ciudad_id": ciudad_id("MDE")}).json()
    ] == ["M1"]


@pytest.fixture()
def escenario_vigencias(api: TestClient, crear_lista, crear_insumo):  # type: ignore[no-untyped-def]
    """BOG: L1 2026-01-01 (A=100, B=50), L2 2026-04-01 (A=110), L3 2026-07-01 (A=125, inactiva).
    MDE: M1 2026-02-01 (A=90)."""
    a = crear_insumo("MAT-001")
    b = crear_insumo("MAT-002")
    c = crear_insumo("MAT-003")
    l1 = crear_lista("L1", "2026-01-01")
    l2 = crear_lista("L2", "2026-04-01")
    l3 = crear_lista("L3", "2026-07-01")
    m1 = crear_lista("M1", "2026-02-01", ciudad="MDE")
    _cargar(api, l1["id"], [{"insumo_id": a["id"], "precio": 100}, {"insumo_id": b["id"], "precio": 50}])
    _cargar(api, l2["id"], [{"insumo_id": a["id"], "precio": 110}])
    _cargar(api, l3["id"], [{"insumo_id": a["id"], "precio": 125}])
    _cargar(api, m1["id"], [{"insumo_id": a["id"], "precio": 90}])
    api.put(f"{API}/listas-precios/{l3['id']}", json={"activo": False})
    return {"a": a["id"], "b": b["id"], "c": c["id"], "l1": l1, "l2": l2, "l3": l3, "m1": m1}


def test_precio_vigente_service_varias_vigencias(escenario_vigencias, db: Session, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    e = escenario_vigencias
    bog, mde = ciudad_id("BOG"), ciudad_id("MDE")
    # antes de cualquier vigencia
    assert service.precio_vigente(db, e["a"], date(2025, 12, 31), bog) is None
    # exactamente en la fecha_desde
    pv = service.precio_vigente(db, e["a"], date(2026, 1, 1), bog)
    assert pv is not None and pv.precio == D("100") and pv.lista_id == e["l1"]["id"]
    # entre vigencias -> la de mayor fecha_desde <= fecha
    pv = service.precio_vigente(db, e["a"], date(2026, 6, 30), bog)
    assert pv is not None and pv.precio == D("110") and pv.fecha_desde == date(2026, 4, 1)
    # la lista L3 está inactiva: se ignora
    pv = service.precio_vigente(db, e["a"], date(2026, 12, 1), bog)
    assert pv is not None and pv.precio == D("110")
    # B no está en L2: cae a la lista anterior que sí lo contiene
    pv = service.precio_vigente(db, e["b"], date(2026, 5, 1), bog)
    assert pv is not None and pv.precio == D("50") and pv.lista_id == e["l1"]["id"]
    # otra ciudad
    pv = service.precio_vigente(db, e["a"], date(2026, 5, 1), mde)
    assert pv is not None and pv.precio == D("90")
    assert service.precio_vigente(db, e["a"], date(2026, 1, 15), mde) is None
    # sin precio
    assert service.precio_vigente(db, e["c"], date(2026, 5, 1), bog) is None


def test_endpoint_precios_vigentes(api: TestClient, escenario_vigencias, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    e = escenario_vigencias
    ids = f"{e['a']},{e['b']},{e['c']}"
    r = api.get(
        f"{API}/precios-vigentes",
        params={"ciudad_id": ciudad_id("BOG"), "fecha": "2026-05-01", "insumo_ids": ids},
    )
    assert r.status_code == 200, r.text
    data = {x["insumo_id"]: x for x in r.json()}
    assert set(data) == {e["a"], e["b"]}  # C sin precio no aparece
    assert D(data[e["a"]]["precio"]) == D("110") and data[e["a"]]["fecha_desde"] == "2026-04-01"
    assert data[e["b"]]["lista_id"] == e["l1"]["id"]

    r = api.get(f"{API}/precios-vigentes", params={"ciudad_id": ciudad_id("BOG"), "insumo_ids": "1,x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    r = api.get(
        f"{API}/precios-vigentes", params={"ciudad_id": 9999, "fecha": "2026-05-01", "insumo_ids": ids}
    )
    assert r.status_code == 404
    assert api.get(f"{API}/precios-vigentes", params={"insumo_ids": ids}).status_code == 422


def test_historico_precios_insumo(api: TestClient, escenario_vigencias, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    e = escenario_vigencias
    hist = api.get(f"{API}/insumos/{e['a']}/precios").json()
    assert [(h["ciudad_codigo"], h["lista_codigo"]) for h in hist] == [
        ("BOG", "L3"),
        ("BOG", "L2"),
        ("BOG", "L1"),
        ("MDE", "M1"),
    ]
    assert D(hist[0]["precio"]) == D("125")
    solo_mde = api.get(f"{API}/insumos/{e['a']}/precios", params={"ciudad_id": ciudad_id("MDE")}).json()
    assert [h["lista_codigo"] for h in solo_mde] == ["M1"]
    assert api.get(f"{API}/insumos/9999/precios").status_code == 404


def test_permisos_listas(client_as, seed_basico, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    body = {"codigo": "L1", "nombre": "x", "ciudad_id": ciudad_id("BOG"), "fecha_desde": "2026-01-01"}
    assert client_as("obra").post(f"{API}/listas-precios", json=body).status_code == 403
    assert client_as("presupuesto").post(f"{API}/listas-precios", json=body).status_code == 201
    assert len(client_as("consulta").get(f"{API}/listas-precios").json()) == 1
