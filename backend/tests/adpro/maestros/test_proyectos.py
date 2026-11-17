"""Proyectos, etapas y torres (nombres de proyecto ficticios)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import AuditLog
from app.modules.adpro.models import Presupuesto

from .conftest import API


def _proyecto(api: TestClient, ciudad_id, codigo: str = "PRY-001", **extra) -> dict:  # type: ignore[no-untyped-def]
    body = {
        "codigo": codigo,
        "nombre": f"Proyecto Demo {codigo}",
        "ciudad_id": ciudad_id("BOG"),
        "tipo": "VIS",
        **extra,
    }
    r = api.post(f"{API}/proyectos", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_crear_proyecto_detalle(api: TestClient, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    p = _proyecto(
        api,
        ciudad_id,
        "pry-001",
        fecha_inicio="2026-02-01",
        fecha_fin_estimada="2027-12-31",
        numero_unidades=480,
    )
    assert p["codigo"] == "PRY-001" and p["estado"] == "PLANEACION"
    assert p["ciudad_codigo"] == "BOG" and p["ciudad_nombre"] == "Bogotá D.C."
    assert p["etapas"] == [] and p["numero_unidades"] == 480
    r = api.get(f"{API}/proyectos/{p['id']}")
    assert r.status_code == 200 and r.json()["fecha_fin_estimada"] == "2027-12-31"
    assert api.get(f"{API}/proyectos/9999").status_code == 404


def test_proyecto_validaciones(api: TestClient, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    _proyecto(api, ciudad_id)
    base = {"nombre": "x", "ciudad_id": ciudad_id("BOG"), "tipo": "VIS"}
    assert api.post(f"{API}/proyectos", json={"codigo": "PRY-001", **base}).status_code == 409
    assert api.post(f"{API}/proyectos", json={"codigo": "P2", **base, "tipo": "ESTRATO"}).status_code == 422
    r = api.post(f"{API}/proyectos", json={"codigo": "P2", **base, "ciudad_id": 9999})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    r = api.post(
        f"{API}/proyectos",
        json={"codigo": "P2", **base, "fecha_inicio": "2027-01-01", "fecha_fin_estimada": "2026-01-01"},
    )
    assert r.status_code == 422
    assert (
        api.post(f"{API}/proyectos", json={"codigo": "P2", **base, "numero_unidades": -1}).status_code == 422
    )


def test_listar_y_filtrar_proyectos(api: TestClient, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    _proyecto(api, ciudad_id, "PRY-B", tipo="NO_VIS")
    _proyecto(api, ciudad_id, "PRY-A")
    api.post(
        f"{API}/proyectos",
        json={
            "codigo": "PRY-C",
            "nombre": "Parque Ficticio",
            "ciudad_id": ciudad_id("MDE"),
            "tipo": "VIP",
            "estado": "EN_EJECUCION",
        },
    )
    assert [p["codigo"] for p in api.get(f"{API}/proyectos").json()] == ["PRY-A", "PRY-B", "PRY-C"]
    assert [p["codigo"] for p in api.get(f"{API}/proyectos", params={"tipo": "NO_VIS"}).json()] == ["PRY-B"]
    assert [p["codigo"] for p in api.get(f"{API}/proyectos", params={"estado": "EN_EJECUCION"}).json()] == [
        "PRY-C"
    ]
    assert [
        p["codigo"] for p in api.get(f"{API}/proyectos", params={"ciudad_id": ciudad_id("MDE")}).json()
    ] == ["PRY-C"]
    assert [p["codigo"] for p in api.get(f"{API}/proyectos", params={"q": "ficticio"}).json()] == ["PRY-C"]
    assert "etapas" not in api.get(f"{API}/proyectos").json()[0]


def test_actualizar_proyecto_y_auditoria_estado(api: TestClient, ciudad_id, db: Session) -> None:  # type: ignore[no-untyped-def]
    p = _proyecto(api, ciudad_id, fecha_inicio="2026-01-01")
    r = api.put(f"{API}/proyectos/{p['id']}", json={"estado": "EN_EJECUCION", "ciudad_id": ciudad_id("SOA")})
    assert (
        r.status_code == 200 and r.json()["estado"] == "EN_EJECUCION" and r.json()["ciudad_codigo"] == "SOA"
    )
    # fecha fin anterior al inicio ya guardado
    r = api.put(f"{API}/proyectos/{p['id']}", json={"fecha_fin_estimada": "2025-01-01"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    # codigo no es actualizable
    assert api.put(f"{API}/proyectos/{p['id']}", json={"codigo": "OTRO"}).status_code == 422
    log = db.scalars(
        select(AuditLog).where(AuditLog.entidad == "proyecto", AuditLog.accion == "ACTUALIZAR")
    ).one()
    assert log.detalle == {"estado_anterior": "PLANEACION", "estado_nuevo": "EN_EJECUCION"}


def test_etapas_y_torres(api: TestClient, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    p = _proyecto(api, ciudad_id)
    r = api.post(f"{API}/proyectos/{p['id']}/etapas", json={"codigo": "et2", "nombre": "Etapa 2", "orden": 2})
    assert r.status_code == 201 and r.json()["codigo"] == "ET2" and r.json()["torres"] == []
    e1 = api.post(
        f"{API}/proyectos/{p['id']}/etapas", json={"codigo": "ET1", "nombre": "Etapa 1", "orden": 1}
    ).json()
    assert (
        api.post(f"{API}/proyectos/{p['id']}/etapas", json={"codigo": "ET1", "nombre": "dup"}).status_code
        == 409
    )
    assert api.post(f"{API}/proyectos/9999/etapas", json={"codigo": "E", "nombre": "x"}).status_code == 404

    t = api.post(
        f"{API}/etapas/{e1['id']}/torres", json={"codigo": "T1", "nombre": "Torre 1", "numero_pisos": 15}
    )
    assert t.status_code == 201 and t.json()["etapa_id"] == e1["id"]
    assert (
        api.post(f"{API}/etapas/{e1['id']}/torres", json={"codigo": "T1", "nombre": "dup"}).status_code == 409
    )
    t2 = api.post(f"{API}/etapas/{e1['id']}/torres", json={"codigo": "T2", "nombre": "Torre 2"}).json()

    det = api.get(f"{API}/proyectos/{p['id']}").json()
    assert [e["codigo"] for e in det["etapas"]] == ["ET1", "ET2"]  # orden
    assert [t["codigo"] for t in det["etapas"][0]["torres"]] == ["T1", "T2"]

    r = api.put(f"{API}/etapas/{e1['id']}", json={"nombre": "Etapa uno", "numero_unidades": 240})
    assert r.status_code == 200 and r.json()["numero_unidades"] == 240 and len(r.json()["torres"]) == 2
    assert api.put(f"{API}/etapas/{e1['id']}", json={"codigo": "ET2"}).status_code == 409
    r = api.put(f"{API}/torres/{t2['id']}", json={"numero_unidades": 60})
    assert r.status_code == 200 and r.json()["numero_unidades"] == 60
    assert api.put(f"{API}/torres/{t2['id']}", json={"codigo": "T1"}).status_code == 409

    assert api.delete(f"{API}/torres/{t2['id']}").status_code == 204
    assert api.delete(f"{API}/torres/{t2['id']}").status_code == 404
    assert api.delete(f"{API}/etapas/{e1['id']}").status_code == 204  # borra sus torres
    assert [e["codigo"] for e in api.get(f"{API}/proyectos/{p['id']}").json()["etapas"]] == ["ET2"]


def test_no_elimina_etapa_con_presupuestos(api: TestClient, ciudad_id, db: Session) -> None:  # type: ignore[no-untyped-def]
    p = _proyecto(api, ciudad_id)
    e = api.post(f"{API}/proyectos/{p['id']}/etapas", json={"codigo": "ET1", "nombre": "Etapa 1"}).json()
    db.add(Presupuesto(proyecto_id=p["id"], etapa_id=e["id"], codigo="PPTO-1", nombre="Presupuesto demo"))
    db.commit()
    r = api.delete(f"{API}/etapas/{e['id']}")
    assert r.status_code == 409 and r.json()["error"]["details"] == {"presupuestos": 1}


def test_permisos_proyectos(client_as, seed_basico, ciudad_id) -> None:  # type: ignore[no-untyped-def]
    body = {"codigo": "P1", "nombre": "Proyecto Demo", "ciudad_id": ciudad_id("BOG"), "tipo": "VIS"}
    assert client_as("obra").post(f"{API}/proyectos", json=body).status_code == 403
    pid = client_as("presupuesto").post(f"{API}/proyectos", json=body).json()["id"]
    cons = client_as("consulta")
    assert cons.get(f"{API}/proyectos/{pid}").status_code == 200
    assert cons.post(f"{API}/proyectos/{pid}/etapas", json={"codigo": "E", "nombre": "x"}).status_code == 403
    assert date.fromisoformat(cons.get(f"{API}/proyectos/{pid}").json()["created_at"][:10])
