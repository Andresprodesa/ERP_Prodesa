"""Tests de humo: health, login JWT, /me, roles y auditoría."""

from __future__ import annotations

from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.models import AuditLog, Rol
from app.core.security import require_role
from tests.conftest import TEST_PASSWORD


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_login_ok_y_me(client: TestClient, make_user, db) -> None:  # type: ignore[no-untyped-def]
    make_user("ana.demo", Rol.PRESUPUESTO)
    r = client.post("/api/auth/login", json={"username": "ana.demo", "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["user"]["rol"] == "presupuesto"
    assert data["expires_in"] > 0

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "ana.demo"

    logs = db.query(AuditLog).filter_by(accion="LOGIN").all()
    assert len(logs) == 1 and logs[0].username == "ana.demo"


def test_login_form_token(client: TestClient, make_user) -> None:  # type: ignore[no-untyped-def]
    make_user("form.demo", Rol.CONSULTA)
    r = client.post("/api/auth/token", data={"username": "form.demo", "password": TEST_PASSWORD})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_credenciales_invalidas(client: TestClient, make_user) -> None:  # type: ignore[no-untyped-def]
    make_user("bad.demo", Rol.CONSULTA)
    r = client.post("/api/auth/login", json={"username": "bad.demo", "password": "otra-clave"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_sin_token_y_token_invalido(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer no-es-un-jwt"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "TOKEN_INVALID"


def test_require_role(app, client_as) -> None:  # type: ignore[no-untyped-def]
    @app.get("/api/_test/solo-presupuesto", dependencies=[Depends(require_role(Rol.PRESUPUESTO))])
    def _solo() -> dict[str, bool]:
        return {"ok": True}

    assert client_as(Rol.PRESUPUESTO).get("/api/_test/solo-presupuesto").status_code == 200
    assert client_as(Rol.ADMIN).get("/api/_test/solo-presupuesto").status_code == 200
    r = client_as(Rol.CONSULTA).get("/api/_test/solo-presupuesto")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_auditoria_solo_admin(client_as) -> None:  # type: ignore[no-untyped-def]
    assert client_as(Rol.ADMIN).get("/api/auditoria").status_code == 200
    assert client_as(Rol.OBRA).get("/api/auditoria").status_code == 403


def test_created_by_automatico(db) -> None:  # type: ignore[no-untyped-def]
    from app.modules.adpro.models import Unidad

    u = Unidad(codigo="XX", nombre="Prueba")
    db.add(u)
    db.commit()
    assert u.created_by == "tester" and u.updated_by == "tester"
    db.info["username"] = "otro"
    u.nombre = "Prueba 2"
    db.commit()
    assert u.created_by == "tester" and u.updated_by == "otro"
