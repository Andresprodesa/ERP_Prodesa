"""Fixtures compartidas de pytest (PROPIEDAD: ARQUITECTO; los agentes no la editan).

Cada test obtiene una BD SQLite EN MEMORIA nueva (StaticPool), creada con
``Base.metadata.create_all``. Fixtures principales:

- ``db``: ``Session`` directa para tests de ``service.py`` (usuario de auditoría "tester").
- ``client``: ``TestClient`` SIN autenticar (misma BD que ``db``).
- ``auth_client``: ``TestClient`` autenticado como ADMIN.
- ``client_as(rol)``: fábrica de clientes autenticados con el rol dado (Rol o str).
- ``make_user(username, rol, password)``: crea un usuario de prueba.
- ``seed_basico``: unidades (UN, M2, M3, KG...) y ciudades (BOG, MDE...) del seed de desarrollo.

Las contraseñas aquí son valores de PRUEBA (no credenciales reales).
"""

from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("JWT_SECRET", "test-secret-solo-para-pytest-0123456789")

from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db_models  # noqa: E402
from app.core.db import SESSION_USER_KEY, build_engine, get_db  # noqa: E402
from app.core.models import Rol, Usuario  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_PASSWORD = "clave-de-prueba-pytest"  # noqa: S105


@pytest.fixture()
def engine() -> Iterator[Engine]:
    eng = build_engine("sqlite://", poolclass=StaticPool)
    db_models.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


@pytest.fixture()
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    session.info[SESSION_USER_KEY] = "tester"
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def app(session_factory: sessionmaker[Session]):  # type: ignore[no-untyped-def]
    application = create_app()

    def _get_db() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    application.dependency_overrides[get_db] = _get_db
    return application


@pytest.fixture()
def make_user(session_factory: sessionmaker[Session]) -> Callable[..., Usuario]:
    def _make(username: str, rol: Rol | str = Rol.ADMIN, password: str = TEST_PASSWORD) -> Usuario:
        with session_factory() as s:
            user = Usuario(
                username=username,
                nombre=f"Usuario prueba {username}",
                rol=Rol(rol),
                hashed_password=hash_password(password),
            )
            s.add(user)
            s.commit()
            s.refresh(user)
            return user

    return _make


@pytest.fixture()
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_as(app, make_user) -> Iterator[Callable[[Rol | str], TestClient]]:  # type: ignore[no-untyped-def]
    clientes: list[TestClient] = []

    def _client(rol: Rol | str = Rol.ADMIN) -> TestClient:
        rol = Rol(rol)
        user = make_user(f"test_{rol.value}_{len(clientes)}", rol)
        token, _ = create_access_token(user)
        c = TestClient(app)
        c.headers.update({"Authorization": f"Bearer {token}"})
        clientes.append(c)
        return c

    yield _client
    for c in clientes:
        c.close()


@pytest.fixture()
def auth_client(client_as) -> TestClient:  # type: ignore[no-untyped-def]
    return client_as(Rol.ADMIN)


@pytest.fixture()
def seed_basico(db: Session) -> Session:
    from app.seed import seed_catalogos

    seed_catalogos(db)
    db.commit()
    return db
