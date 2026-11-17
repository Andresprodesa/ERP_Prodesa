"""Fixtures del submódulo maestros (datos 100 % sintéticos)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.adpro.models import Ciudad, Unidad

API = "/api/adpro/maestros"


@pytest.fixture()
def api(auth_client: TestClient, seed_basico: Session) -> TestClient:
    """Cliente ADMIN con unidades y ciudades del seed básico."""
    return auth_client


@pytest.fixture()
def unidad_id(seed_basico: Session) -> Callable[[str], int]:
    def _get(codigo: str) -> int:
        return seed_basico.scalar(select(Unidad.id).where(Unidad.codigo == codigo))  # type: ignore[return-value]

    return _get


@pytest.fixture()
def ciudad_id(seed_basico: Session) -> Callable[[str], int]:
    def _get(codigo: str) -> int:
        return seed_basico.scalar(select(Ciudad.id).where(Ciudad.codigo == codigo))  # type: ignore[return-value]

    return _get


@pytest.fixture()
def crear_insumo(api: TestClient, unidad_id: Callable[[str], int]) -> Callable[..., dict[str, Any]]:
    def _crear(
        codigo: str, descripcion: str = "Insumo demo", unidad: str = "UN", tipo: str = "MAT"
    ) -> dict[str, Any]:
        r = api.post(
            f"{API}/insumos",
            json={"codigo": codigo, "descripcion": descripcion, "unidad_id": unidad_id(unidad), "tipo": tipo},
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _crear


@pytest.fixture()
def crear_lista(api: TestClient, ciudad_id: Callable[[str], int]) -> Callable[..., dict[str, Any]]:
    def _crear(codigo: str, fecha_desde: str, ciudad: str = "BOG", **extra: Any) -> dict[str, Any]:
        r = api.post(
            f"{API}/listas-precios",
            json={
                "codigo": codigo,
                "nombre": f"Lista {codigo}",
                "ciudad_id": ciudad_id(ciudad),
                "fecha_desde": fecha_desde,
                **extra,
            },
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _crear


@pytest.fixture()
def crear_edt(api: TestClient) -> Callable[..., dict[str, Any]]:
    def _crear(nivel: str, codigo: str, parent_id: int | None = None, **extra: Any) -> dict[str, Any]:
        body = {
            "nivel": nivel,
            "codigo": codigo,
            "descripcion": f"Nodo {codigo}",
            "parent_id": parent_id,
            **extra,
        }
        r = api.post(f"{API}/edt", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    return _crear
