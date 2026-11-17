"""Unidades y ciudades: CRUD, normalización de código, duplicados y permisos."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.models import Rol

from .conftest import API


def test_listar_unidades_seed_ordenadas(api: TestClient) -> None:
    r = api.get(f"{API}/unidades")
    assert r.status_code == 200
    codigos = [u["codigo"] for u in r.json()]
    assert "M2" in codigos and codigos == sorted(codigos)
    assert {"created_at", "updated_at", "created_by", "updated_by"} <= set(r.json()[0])


def test_crear_unidad_normaliza_codigo_y_duplicado(api: TestClient) -> None:
    r = api.post(f"{API}/unidades", json={"codigo": " cjo ", "nombre": "Cajón"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["codigo"] == "CJO" and body["activo"] is True
    assert body["created_by"].startswith("test_admin")

    r = api.post(f"{API}/unidades", json={"codigo": "CJO", "nombre": "Otro"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"
    assert "CJO" in r.json()["error"]["message"]


def test_actualizar_e_inactivar_unidad_y_filtros(api: TestClient) -> None:
    uid = api.post(f"{API}/unidades", json={"codigo": "PAR", "nombre": "Par"}).json()["id"]
    r = api.put(f"{API}/unidades/{uid}", json={"nombre": "Pareja", "activo": False})
    assert r.status_code == 200
    assert r.json()["nombre"] == "Pareja" and r.json()["activo"] is False

    inactivas = api.get(f"{API}/unidades", params={"activo": False}).json()
    assert [u["codigo"] for u in inactivas] == ["PAR"]
    buscadas = api.get(f"{API}/unidades", params={"q": "parej"}).json()
    assert [u["codigo"] for u in buscadas] == ["PAR"]


def test_actualizar_unidad_codigo_duplicado_y_404(api: TestClient) -> None:
    uid = api.post(f"{API}/unidades", json={"codigo": "ROL", "nombre": "Rollo"}).json()["id"]
    assert api.put(f"{API}/unidades/{uid}", json={"codigo": "m2"}).status_code == 409
    r = api.put(f"{API}/unidades/99999", json={"nombre": "x"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_unidad_validaciones_esquema(api: TestClient) -> None:
    r = api.post(f"{API}/unidades", json={"codigo": "", "nombre": "Vacía"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    r = api.post(f"{API}/unidades", json={"codigo": "ABCDEFGHIJK", "nombre": "Muy largo"})
    assert r.status_code == 422
    r = api.post(f"{API}/unidades", json={"codigo": "X Y", "nombre": "Con espacio"})
    assert r.status_code == 422
    r = api.post(f"{API}/unidades", json={"codigo": "XY", "nombre": "x", "campo_raro": 1})
    assert r.status_code == 422


def test_ciudades_crud(api: TestClient) -> None:
    r = api.post(
        f"{API}/ciudades",
        json={
            "codigo": "ciu",
            "nombre": "Ciudad Ficticia",
            "departamento": "Depto Demo",
            "regional": "Centro",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["codigo"] == "CIU"
    assert api.post(f"{API}/ciudades", json={"codigo": "BOG", "nombre": "Dup"}).status_code == 409

    r = api.put(f"{API}/ciudades/{cid}", json={"regional": "Occidente", "activo": False})
    assert r.status_code == 200 and r.json()["regional"] == "Occidente" and r.json()["activo"] is False

    activas = [c["codigo"] for c in api.get(f"{API}/ciudades", params={"activo": True}).json()]
    assert "CIU" not in activas and "BOG" in activas
    assert [c["codigo"] for c in api.get(f"{API}/ciudades", params={"q": "medell"}).json()] == ["MDE"]


def test_permisos_unidades(client_as, seed_basico, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    assert client.get(f"{API}/unidades").status_code == 401
    consulta = client_as(Rol.CONSULTA)
    assert consulta.get(f"{API}/unidades").status_code == 200
    r = consulta.post(f"{API}/unidades", json={"codigo": "ZZ", "nombre": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert (
        client_as(Rol.OBRA).post(f"{API}/unidades", json={"codigo": "ZZ", "nombre": "x"}).status_code == 403
    )
    assert (
        client_as(Rol.PRESUPUESTO).post(f"{API}/unidades", json={"codigo": "ZZ", "nombre": "x"}).status_code
        == 201
    )
