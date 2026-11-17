"""EDT presupuestal: jerarquía CAPITULO -> DETALLE -> GRUPO -> ITEM, códigos, árbol y ruta."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.adpro.models import Apu

from .conftest import API


@pytest.fixture()
def edt(crear_edt, unidad_id) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """01 Preliminares > 01.01 > 01.01.001 > (0001, 0002); 02 Estructura > 02.01."""
    m2 = unidad_id("M2")
    c1 = crear_edt("CAPITULO", "01", descripcion="Preliminares", orden=1)
    d1 = crear_edt("DETALLE", "01.01", c1["id"], descripcion="Localización")
    g1 = crear_edt("GRUPO", "01.01.001", d1["id"], descripcion="Replanteo")
    i2 = crear_edt("ITEM", "01.01.001.0002", g1["id"], unidad_id=m2, orden=2)
    i1 = crear_edt(
        "ITEM", "01.01.001.0001", g1["id"], unidad_id=m2, orden=1, notas="Incluye comisión topográfica"
    )
    c2 = crear_edt("CAPITULO", "02", descripcion="Estructura", orden=2)
    d2 = crear_edt("DETALLE", "02.01", c2["id"])
    return {"c1": c1, "d1": d1, "g1": g1, "i1": i1, "i2": i2, "c2": c2, "d2": d2, "m2": m2}


def test_crear_nodos_ok(edt: dict[str, Any]) -> None:
    i1 = edt["i1"]
    assert i1["nivel"] == "ITEM" and i1["unidad_codigo"] == "M2" and i1["tiene_apu"] is False
    assert i1["notas"] == "Incluye comisión topográfica"
    assert edt["c1"]["unidad_id"] is None and edt["c1"]["parent_id"] is None
    assert edt["c2"]["orden"] == 2 and edt["d2"]["orden"] == 0


@pytest.mark.parametrize(
    ("nivel", "codigo", "padre", "con_unidad", "fragmento"),
    [
        ("CAPITULO", "03", "c1", False, "no puede tener padre"),
        ("CAPITULO", "03.01", None, False, "no lleva punto"),
        ("DETALLE", "01.02", None, False, "requiere un padre"),
        ("DETALLE", "01.01.002", "d1", False, "debe colgar de un CAPITULO"),
        ("GRUPO", "01.002", "c1", False, "debe colgar de un DETALLE"),
        ("ITEM", "01.01.0009", "d1", True, "debe colgar de un GRUPO"),
        ("ITEM", "01.01.001.0003", "g1", False, "requieren unidad"),
        ("GRUPO", "01.01.002", "d1", True, "Solo los nodos de nivel ITEM"),
        ("DETALLE", "02.05", "c1", False, "código del padre"),
        ("GRUPO", "01.01.002.1", "d1", False, "código del padre"),
        ("DETALLE", "0102", "c1", False, "código del padre"),
    ],
)
def test_reglas_jerarquia(
    api: TestClient,
    edt: dict[str, Any],
    nivel: str,
    codigo: str,
    padre: str | None,
    con_unidad: bool,
    fragmento: str,
) -> None:
    body = {
        "nivel": nivel,
        "codigo": codigo,
        "descripcion": "x",
        "parent_id": edt[padre]["id"] if padre else None,
        "unidad_id": edt["m2"] if con_unidad else None,
    }
    r = api.post(f"{API}/edt", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "BUSINESS_RULE"
    assert fragmento in r.json()["error"]["message"]


def test_codigo_edt_formato_y_duplicado(api: TestClient, edt: dict[str, Any]) -> None:
    for malo in ("01..02", "01.", "01-02", "01_02"):
        r = api.post(f"{API}/edt", json={"nivel": "CAPITULO", "codigo": malo, "descripcion": "x"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR", malo
    r = api.post(f"{API}/edt", json={"nivel": "CAPITULO", "codigo": "01", "descripcion": "dup"})
    assert r.status_code == 409
    r = api.post(
        f"{API}/edt", json={"nivel": "DETALLE", "codigo": "01.01", "descripcion": "x", "parent_id": 9999}
    )
    assert r.status_code == 422 and "no existe" in r.json()["error"]["message"]
    r = api.post(f"{API}/edt", json={"nivel": "NIVEL5", "codigo": "09", "descripcion": "x"})
    assert r.status_code == 422


def test_padre_inactivo_no_admite_hijos(api: TestClient, edt: dict[str, Any]) -> None:
    assert api.put(f"{API}/edt/{edt['d2']['id']}", json={"activo": False}).status_code == 200
    r = api.post(
        f"{API}/edt",
        json={"nivel": "GRUPO", "codigo": "02.01.001", "descripcion": "x", "parent_id": edt["d2"]["id"]},
    )
    assert r.status_code == 422 and "inactivo" in r.json()["error"]["message"]


def test_listar_edt_filtros(api: TestClient, edt: dict[str, Any]) -> None:
    page = api.get(f"{API}/edt").json()
    assert page["total"] == 7
    assert [n["codigo"] for n in page["items"]][:3] == ["01", "01.01", "01.01.001"]
    items = api.get(f"{API}/edt", params={"nivel": "ITEM"}).json()
    assert [n["codigo"] for n in items["items"]] == ["01.01.001.0001", "01.01.001.0002"]
    hijos = api.get(f"{API}/edt", params={"parent_id": edt["c1"]["id"]}).json()
    assert [n["codigo"] for n in hijos["items"]] == ["01.01"]
    assert api.get(f"{API}/edt", params={"q": "replanteo"}).json()["total"] == 1
    page = api.get(f"{API}/edt", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 7 and len(page["items"]) == 2


def test_arbol(api: TestClient, edt: dict[str, Any]) -> None:
    arbol = api.get(f"{API}/edt/arbol").json()
    assert [c["codigo"] for c in arbol] == ["01", "02"]
    grupo = arbol[0]["hijos"][0]["hijos"][0]
    assert grupo["codigo"] == "01.01.001"
    assert [i["codigo"] for i in grupo["hijos"]] == ["01.01.001.0001", "01.01.001.0002"]  # por orden
    assert grupo["hijos"][0]["hijos"] == []

    solo_cap = api.get(f"{API}/edt/arbol", params={"capitulo_id": edt["c2"]["id"]}).json()
    assert [c["codigo"] for c in solo_cap] == ["02"] and solo_cap[0]["hijos"][0]["codigo"] == "02.01"

    hasta_detalle = api.get(f"{API}/edt/arbol", params={"hasta_nivel": "DETALLE"}).json()
    assert hasta_detalle[0]["hijos"][0]["hijos"] == []

    r = api.get(f"{API}/edt/arbol", params={"capitulo_id": edt["d1"]["id"]})
    assert r.status_code == 422
    assert api.get(f"{API}/edt/arbol", params={"capitulo_id": 9999}).status_code == 404


def test_arbol_excluye_subarbol_inactivo(api: TestClient, edt: dict[str, Any]) -> None:
    api.put(f"{API}/edt/{edt['g1']['id']}", json={"activo": False})
    arbol = api.get(f"{API}/edt/arbol", params={"activo": True}).json()
    assert arbol[0]["hijos"][0]["hijos"] == []  # grupo inactivo e ítems fuera
    completo = api.get(f"{API}/edt/arbol").json()
    assert len(completo[0]["hijos"][0]["hijos"][0]["hijos"]) == 2


def test_detalle_con_ruta_y_tiene_apu(api: TestClient, edt: dict[str, Any], db: Session) -> None:
    db.add(Apu(item_id=edt["i1"]["id"]))
    db.commit()
    r = api.get(f"{API}/edt/{edt['i1']['id']}")
    assert r.status_code == 200
    det = r.json()
    assert [n["codigo"] for n in det["ruta"]] == ["01", "01.01", "01.01.001", "01.01.001.0001"]
    assert det["ruta"][0]["nivel"] == "CAPITULO" and det["tiene_apu"] is True
    assert api.get(f"{API}/edt/9999").status_code == 404
    items = api.get(f"{API}/edt", params={"nivel": "ITEM"}).json()["items"]
    assert [n["tiene_apu"] for n in items] == [True, False]
    arbol = api.get(f"{API}/edt/arbol").json()
    assert arbol[0]["hijos"][0]["hijos"][0]["hijos"][0]["tiene_apu"] is True


def test_actualizar_nodo(api: TestClient, edt: dict[str, Any], unidad_id: Callable[[str], int]) -> None:
    url = f"{API}/edt/{edt['i1']['id']}"
    r = api.put(
        url, json={"descripcion": "Localización y replanteo", "unidad_id": unidad_id("ML"), "orden": 5}
    )
    assert r.status_code == 200 and r.json()["unidad_codigo"] == "ML" and r.json()["orden"] == 5
    assert api.put(url, json={"unidad_id": None}).status_code == 422  # ítem sin unidad
    assert api.put(f"{API}/edt/{edt['c1']['id']}", json={"unidad_id": unidad_id("M2")}).status_code == 422
    assert api.put(url, json={"codigo": "01.01.001.9999"}).status_code == 422  # inmutable
    assert api.put(url, json={"nivel": "GRUPO"}).status_code == 422
    assert api.put(f"{API}/edt/9999", json={"descripcion": "x"}).status_code == 404


def test_reactivar_hijo_con_padre_inactivo(api: TestClient, edt: dict[str, Any]) -> None:
    api.put(f"{API}/edt/{edt['i1']['id']}", json={"activo": False})
    api.put(f"{API}/edt/{edt['g1']['id']}", json={"activo": False})
    r = api.put(f"{API}/edt/{edt['i1']['id']}", json={"activo": True})
    assert r.status_code == 422 and "padre" in r.json()["error"]["message"]


def test_permisos_edt(client_as, seed_basico) -> None:  # type: ignore[no-untyped-def]
    body = {"nivel": "CAPITULO", "codigo": "01", "descripcion": "Preliminares"}
    assert client_as("consulta").post(f"{API}/edt", json=body).status_code == 403
    assert client_as("obra").post(f"{API}/edt", json=body).status_code == 403
    assert client_as("presupuesto").post(f"{API}/edt", json=body).status_code == 201
    assert client_as("consulta").get(f"{API}/edt/arbol").status_code == 200
