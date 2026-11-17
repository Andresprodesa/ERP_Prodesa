"""Fixtures del submódulo presupuesto (escenario sintético compartido con apu)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.adpro.apu.escenario import crear_escenario

BASE = "/api/adpro/presupuestos"


@pytest.fixture()
def esc(db: Session) -> dict[str, int]:
    return crear_escenario(db)


@pytest.fixture()
def crear_v1(auth_client: TestClient, esc: dict[str, int]) -> Callable[..., dict[str, Any]]:
    """Crea presupuesto + versión 1 (FIC, precios 2026-03-01, BOG, A8 % I2 % U5 % IVA19 %) con:

    - Muro      100.5 M2 × 12100 (APU)          = 1 216 050
    - Concreto  12.35 M3 × 393416.6640 (APU)    = 4 858 695.8004 -> 4 858 696
    - Losa      3.3 M2 × 85000.5 (MANUAL)       =   280 501.65   ->   280 502
    """

    def _crear(con_lineas: bool = True) -> dict[str, Any]:
        p = auth_client.post(
            BASE,
            json={
                "proyecto_id": esc["proyecto"],
                "etapa_id": esc["etapa"],
                "codigo": "ppto-01",
                "nombre": "Ppto demo",
            },
        )
        assert p.status_code == 201, p.text
        pid = p.json()["id"]
        v = auth_client.post(
            f"{BASE}/{pid}/versiones",
            json={
                "tipo": "FIC",
                "nombre": "FIC inicial",
                "fecha_precios": "2026-03-01",
                "administracion_pct": "0.08",
                "imprevistos_pct": "0.02",
                "utilidad_pct": "0.05",
                "iva_utilidad_pct": "0.19",
            },
        )
        assert v.status_code == 201, v.text
        vid = v.json()["id"]
        if con_lineas:
            r = auth_client.post(
                f"{BASE}/versiones/{vid}/lineas/lote",
                json={
                    "lineas": [
                        {"item_id": esc["muro"], "cantidad": "100.5"},
                        {"item_id": esc["concreto"], "cantidad": "12.35"},
                        {"item_id": esc["losa"], "cantidad": "3.3", "valor_unitario": "85000.5"},
                    ]
                },
            )
            assert r.status_code == 200 and r.json() == {"creadas": 3, "errores": []}, r.text
        return {"pid": pid, "vid": vid}

    return _crear
