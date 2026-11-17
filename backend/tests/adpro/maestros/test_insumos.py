"""Insumos: CRUD, filtros, paginación y regla de código en uso."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.adpro.enums import NivelEdt
from app.modules.adpro.models import Apu, ApuInsumo, EdtNodo

from .conftest import API


def test_crear_y_obtener_insumo(api: TestClient, unidad_id: Callable[[str], int]) -> None:
    r = api.post(
        f"{API}/insumos",
        json={
            "codigo": "mat-001",
            "descripcion": "Cemento gris uso general (demo)",
            "unidad_id": unidad_id("BTO"),
            "tipo": "MAT",
            "observaciones": "Bulto 50 kg",
        },
    )
    assert r.status_code == 201, r.text
    ins = r.json()
    assert ins["codigo"] == "MAT-001" and ins["unidad_codigo"] == "BTO" and ins["tipo"] == "MAT"
    r = api.get(f"{API}/insumos/{ins['id']}")
    assert r.status_code == 200 and r.json()["descripcion"] == "Cemento gris uso general (demo)"
    assert api.get(f"{API}/insumos/9999").status_code == 404


def test_insumo_validaciones(api: TestClient, unidad_id: Callable[[str], int], crear_insumo) -> None:  # type: ignore[no-untyped-def]
    crear_insumo("MAT-001")
    base = {"descripcion": "x", "unidad_id": unidad_id("UN"), "tipo": "MAT"}
    assert api.post(f"{API}/insumos", json={"codigo": "mat-001", **base}).status_code == 409
    r = api.post(f"{API}/insumos", json={"codigo": "MAT-002", **base, "tipo": "XX"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    r = api.post(f"{API}/insumos", json={"codigo": "MAT-002", **base, "unidad_id": 9999})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    assert "unidad" in r.json()["error"]["message"].lower()


def test_insumo_con_unidad_inactiva(api: TestClient, unidad_id: Callable[[str], int]) -> None:
    api.put(f"{API}/unidades/{unidad_id('GAL')}", json={"activo": False})
    r = api.post(
        f"{API}/insumos",
        json={"codigo": "MAT-9", "descripcion": "x", "unidad_id": unidad_id("GAL"), "tipo": "MAT"},
    )
    assert r.status_code == 422 and "inactiva" in r.json()["error"]["message"]


def test_listar_insumos_filtros_y_paginacion(api: TestClient, crear_insumo, unidad_id) -> None:  # type: ignore[no-untyped-def]
    crear_insumo("MAT-003", "Arena de peña (demo)", "M3", "MAT")
    crear_insumo("MAT-001", "Cemento gris (demo)", "BTO", "MAT")
    crear_insumo("MO-001", "Cuadrilla oficial + ayudante (demo)", "DIA", "MO")
    crear_insumo("EQ-001", "Mezcladora 1 bulto (demo)", "DIA", "EQ")
    crear_insumo("MAT-002", "Gravilla (demo)", "M3", "MAT")

    page = api.get(f"{API}/insumos").json()
    assert page["total"] == 5 and page["limit"] == 50 and page["offset"] == 0
    assert [i["codigo"] for i in page["items"]] == ["EQ-001", "MAT-001", "MAT-002", "MAT-003", "MO-001"]

    page = api.get(f"{API}/insumos", params={"tipo": "MAT", "limit": 2, "offset": 1}).json()
    assert page["total"] == 3 and [i["codigo"] for i in page["items"]] == ["MAT-002", "MAT-003"]

    assert [i["codigo"] for i in api.get(f"{API}/insumos", params={"q": "CEMENTO"}).json()["items"]] == [
        "MAT-001"
    ]
    assert [i["codigo"] for i in api.get(f"{API}/insumos", params={"q": "mo-"}).json()["items"]] == ["MO-001"]
    by_unit = api.get(f"{API}/insumos", params={"unidad_id": unidad_id("M3")}).json()
    assert by_unit["total"] == 2
    assert api.get(f"{API}/insumos", params={"limit": 0}).status_code == 422
    assert api.get(f"{API}/insumos", params={"limit": 501}).status_code == 422


def test_actualizar_insumo_parcial(api: TestClient, crear_insumo, unidad_id) -> None:  # type: ignore[no-untyped-def]
    ins = crear_insumo("MAT-001", "Cemento", "BTO")
    r = api.put(f"{API}/insumos/{ins['id']}", json={"descripcion": "Cemento gris", "activo": False})
    assert r.status_code == 200
    assert r.json()["descripcion"] == "Cemento gris" and r.json()["activo"] is False
    assert r.json()["unidad_codigo"] == "BTO"
    assert api.get(f"{API}/insumos", params={"activo": True}).json()["total"] == 0

    r = api.put(f"{API}/insumos/{ins['id']}", json={"unidad_id": unidad_id("KG")})
    assert r.status_code == 200 and r.json()["unidad_codigo"] == "KG"
    r = api.put(f"{API}/insumos/{ins['id']}", json={"descripcion": None})
    assert r.status_code == 422


def test_cambiar_codigo_insumo_libre_y_en_uso(
    api: TestClient, crear_insumo, db: Session, unidad_id: Callable[[str], int]
) -> None:  # type: ignore[no-untyped-def]
    ins: dict[str, Any] = crear_insumo("MAT-001")
    otro = crear_insumo("MAT-002")
    r = api.put(f"{API}/insumos/{ins['id']}", json={"codigo": "mat-010"})
    assert r.status_code == 200 and r.json()["codigo"] == "MAT-010"
    assert api.put(f"{API}/insumos/{ins['id']}", json={"codigo": "MAT-002"}).status_code == 409

    # Lo usamos en un APU (directamente en BD: el submódulo APU es de otro agente)
    cap = EdtNodo(nivel=NivelEdt.CAPITULO, codigo="01", descripcion="Cap")
    db.add(cap)
    db.flush()
    det = EdtNodo(nivel=NivelEdt.DETALLE, codigo="01.01", descripcion="Det", parent_id=cap.id)
    db.add(det)
    db.flush()
    gru = EdtNodo(nivel=NivelEdt.GRUPO, codigo="01.01.001", descripcion="Gru", parent_id=det.id)
    db.add(gru)
    db.flush()
    item = EdtNodo(
        nivel=NivelEdt.ITEM,
        codigo="01.01.001.0001",
        descripcion="Item",
        parent_id=gru.id,
        unidad_id=unidad_id("M2"),
    )
    db.add(item)
    db.flush()
    apu = Apu(item_id=item.id)
    db.add(apu)
    db.flush()
    db.add(ApuInsumo(apu_id=apu.id, insumo_id=otro["id"], cantidad=Decimal("1")))
    db.commit()

    r = api.put(f"{API}/insumos/{otro['id']}", json={"codigo": "MAT-099"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    # Mismo código (sin cambio) sí se permite
    assert (
        api.put(f"{API}/insumos/{otro['id']}", json={"codigo": "MAT-002", "descripcion": "ok"}).status_code
        == 200
    )


def test_permisos_insumos(client_as, seed_basico, unidad_id) -> None:  # type: ignore[no-untyped-def]
    body = {"codigo": "MAT-1", "descripcion": "x", "unidad_id": unidad_id("UN"), "tipo": "MAT"}
    assert client_as("consulta").post(f"{API}/insumos", json=body).status_code == 403
    assert client_as("obra").post(f"{API}/insumos", json=body).status_code == 403
    assert client_as("presupuesto").post(f"{API}/insumos", json=body).status_code == 201
    assert client_as("obra").get(f"{API}/insumos").json()["total"] == 1
