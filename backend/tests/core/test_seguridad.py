"""Seguridad transversal (regresiones de la revisión de arquitectura).

- Toda ruta no pública exige token; el rol consulta no escribe; auditoría solo admin.
- JWT_SECRET: fuera de local/test se exige uno propio (>= 32); en local nunca se firma con el
  valor de ejemplo público del repositorio.
- Login: se ejecuta bcrypt aunque el usuario no exista (sin oráculo de tiempo).
- ``DataError`` de la BD (rango INTEGER/NUMERIC en PostgreSQL) -> 422, no 500.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError

from app.core import config as config_mod
from app.core import security
from app.core.config import DEV_JWT_SECRET, Settings
from app.core.errors import AuthError
from app.core.models import Rol

RUTAS_PUBLICAS = {("GET", "/api/health"), ("POST", "/api/auth/login"), ("POST", "/api/auth/token")}


def _rutas(app) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    return sorted(
        (m, r.path)
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/")
        for m in r.methods
    )


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


# --- Control de acceso ---------------------------------------------------------------------
def test_toda_ruta_no_publica_exige_token(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    fallos = [
        (m, p, client.request(m, _url(p)).status_code) for m, p in _rutas(app) if (m, p) not in RUTAS_PUBLICAS
    ]
    assert [f for f in fallos if f[2] != 401] == []


def test_rol_consulta_no_puede_escribir_en_ninguna_ruta(
    app,
    client_as: Callable[[Rol | str], TestClient],  # type: ignore[no-untyped-def]
) -> None:
    c = client_as(Rol.CONSULTA)
    fallos = []
    for metodo, path in _rutas(app):
        if metodo == "GET" or (metodo, path) in RUTAS_PUBLICAS:
            continue
        r = c.request(metodo, _url(path), json={})
        if r.status_code != 403:
            fallos.append((metodo, path, r.status_code))
    assert fallos == []


def test_auditoria_solo_admin(client_as: Callable[[Rol | str], TestClient]) -> None:
    for rol in (Rol.PRESUPUESTO, Rol.OBRA, Rol.CONSULTA):
        assert client_as(rol).get("/api/auditoria").status_code == 403
    assert client_as(Rol.ADMIN).get("/api/auditoria").status_code == 200


def test_id_fuera_de_rango_int32_responde_404_o_422(client_as: Callable[[Rol | str], TestClient]) -> None:
    r = client_as(Rol.CONSULTA).get("/api/adpro/presupuestos/versiones/99999999999")
    assert r.status_code in (404, 422), r.text


def test_data_error_de_bd_responde_422(app) -> None:  # type: ignore[no-untyped-def]
    def _falla() -> None:
        raise DataError("UPDATE x", {}, Exception("numeric field overflow"))

    app.add_api_route("/api/_prueba_data_error", _falla, methods=["GET"])
    with TestClient(app) as c:
        r = c.get("/api/_prueba_data_error")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


# --- JWT_SECRET -----------------------------------------------------------------------------
@pytest.mark.parametrize("entorno", ["staging", "ci", "prod", "production"])
@pytest.mark.parametrize("secreto", [DEV_JWT_SECRET, "corto", ""])
def test_jwt_secret_debil_rechazado_fuera_de_local(entorno: str, secreto: str) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(ENVIRONMENT=entorno, JWT_SECRET=secreto, DATABASE_URL="postgresql+psycopg://x@h/db")


def test_jwt_secret_propio_aceptado_en_staging() -> None:
    s = Settings(ENVIRONMENT="staging", JWT_SECRET="x" * 40, DATABASE_URL="postgresql+psycopg://x@h/db")
    assert s.JWT_SECRET == "x" * 40


def test_local_sin_secreto_usa_uno_aleatorio_persistido(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archivo = tmp_path / ".jwt_secret.local"
    monkeypatch.setattr(config_mod, "_ARCHIVO_SECRETO_LOCAL", archivo)
    s1 = Settings(ENVIRONMENT="local", JWT_SECRET=DEV_JWT_SECRET)
    assert s1.JWT_SECRET != DEV_JWT_SECRET and len(s1.JWT_SECRET) >= 32
    assert archivo.read_text(encoding="utf-8") == s1.JWT_SECRET
    assert Settings(ENVIRONMENT="local", JWT_SECRET="").JWT_SECRET == s1.JWT_SECRET  # sobrevive a reinicios


# --- Login ------------------------------------------------------------------------------
def test_login_verifica_bcrypt_aunque_el_usuario_no_exista(db, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    llamadas: list[str | None] = []
    original = security.verify_password

    def _espia(password: str, hashed: str | None) -> bool:
        llamadas.append(hashed)
        return original(password, hashed)

    monkeypatch.setattr(security, "verify_password", _espia)
    with pytest.raises(AuthError):
        security.authenticate(db, "no-existe", "cualquier-cosa")
    assert llamadas == [security._HASH_FICTICIO]
