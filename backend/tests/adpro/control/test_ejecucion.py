"""Ejecución / avance mensual (§5.3)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.core.models import AuditLog
from tests.adpro.control.conftest import Escenario

D = Decimal
URL = "/api/adpro/control/ejecucion"


def _lote(esc: Escenario, periodo: str, registros: list[dict]) -> dict:  # type: ignore[type-arg]
    return {"presupuesto_id": esc.presupuesto.id, "periodo": periodo, "registros": registros}


def test_upsert_lote_y_listado(client_as, escenario: Escenario, db) -> None:
    c = client_as("obra")
    r = c.put(
        URL,
        json=_lote(
            escenario,
            "2026-09",
            [
                {
                    "item_id": escenario.item_a.id,
                    "valor_ejecutado": "300000",
                    "cantidad_ejecutada": "25",
                    "avance_fisico_pct": "0.25",
                },
                {
                    "item_id": escenario.item_c.id,
                    "valor_ejecutado": "200000",
                    "avance_fisico_pct": "0.3",
                    "observacion": "Corte demo",
                },
            ],
        ),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"creados": 2, "actualizados": 0, "advertencias": []}

    # Upsert: actualiza A en el mismo periodo, crea en el siguiente
    r = c.put(
        URL,
        json=_lote(
            escenario,
            "2026-09",
            [{"item_id": escenario.item_a.id, "valor_ejecutado": "310000", "avance_fisico_pct": "0.26"}],
        ),
    )
    assert r.json()["creados"] == 0 and r.json()["actualizados"] == 1
    r = c.put(
        URL,
        json=_lote(
            escenario,
            "2026-10",
            [{"item_id": escenario.item_a.id, "valor_ejecutado": "400000", "avance_fisico_pct": "0.5"}],
        ),
    )
    assert r.json()["creados"] == 1

    filas = c.get(URL, params={"presupuesto_id": escenario.presupuesto.id}).json()
    assert [(f["periodo"], f["item_codigo"]) for f in filas] == [
        ("2026-09", "01.01.001.0001"),
        ("2026-09", "02.01.001.0001"),
        ("2026-10", "01.01.001.0001"),
    ]
    assert D(filas[0]["valor_ejecutado"]) == D("310000") and filas[0]["cantidad_ejecutada"] is None
    assert filas[1]["observacion"] == "Corte demo" and "created_at" in filas[1]
    assert (
        len(c.get(URL, params={"presupuesto_id": escenario.presupuesto.id, "periodo": "2026-10"}).json()) == 1
    )
    assert (
        len(
            c.get(
                URL, params={"presupuesto_id": escenario.presupuesto.id, "item_id": escenario.item_c.id}
            ).json()
        )
        == 1
    )
    assert (
        len(c.get(URL, params={"presupuesto_id": escenario.presupuesto.id, "desde": "2026-10"}).json()) == 1
    )
    assert (
        len(c.get(URL, params={"presupuesto_id": escenario.presupuesto.id, "hasta": "2026-09"}).json()) == 2
    )

    r = c.get(f"{URL}/periodos", params={"presupuesto_id": escenario.presupuesto.id})
    assert r.status_code == 200 and r.json() == ["2026-09", "2026-10"]
    assert db.scalars(select(AuditLog).where(AuditLog.entidad == "ejecucion")).first() is not None


def test_advertencias_avance_baja_y_item_fuera_de_version(client_as, escenario: Escenario) -> None:
    c = client_as("admin")
    c.put(
        URL,
        json=_lote(
            escenario,
            "2026-09",
            [{"item_id": escenario.item_a.id, "valor_ejecutado": "1", "avance_fisico_pct": "0.4"}],
        ),
    )
    r = c.put(
        URL,
        json=_lote(
            escenario,
            "2026-10",
            [
                {"item_id": escenario.item_a.id, "valor_ejecutado": "1", "avance_fisico_pct": "0.3"},
                {"item_id": escenario.item_d.id, "valor_ejecutado": "1", "avance_fisico_pct": "0.1"},
            ],
        ),
    )
    adv = r.json()["advertencias"]
    assert any("baja" in a and "01.01.001.0001" in a for a in adv)
    assert any("02.01.001.0002" in a and "no está en la versión de control" in a for a in adv)


def test_validaciones_lote(client_as, escenario: Escenario, db) -> None:
    c = client_as("obra")
    reg = {"item_id": escenario.item_a.id, "valor_ejecutado": "1", "avance_fisico_pct": "0.1"}
    assert c.put(URL, json=_lote(escenario, "2026-13", [reg])).status_code == 422
    assert (
        c.put(URL, json=_lote(escenario, "2026-09", [{**reg, "avance_fisico_pct": "1.5"}])).status_code == 422
    )
    assert c.put(URL, json=_lote(escenario, "2026-09", [])).status_code == 422
    r = c.put(URL, json=_lote(escenario, "2026-09", [reg, reg]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    r = c.put(URL, json=_lote(escenario, "2026-09", [{**reg, "item_id": escenario.cap1.id}]))
    assert r.status_code == 422
    # compromiso de otro presupuesto
    from app.modules.adpro.enums import TipoCompromiso
    from app.modules.adpro.models import Compromiso, Presupuesto

    p2 = Presupuesto(proyecto_id=escenario.proyecto.id, codigo="PPTO-X", nombre="Otro")
    db.add(p2)
    db.flush()
    comp = Compromiso(
        presupuesto_id=p2.id,
        tipo=TipoCompromiso.CONTRATO,
        numero="C-1",
        fecha=__import__("datetime").date(2026, 9, 1),
        tercero="Contratista Demo",
    )
    db.add(comp)
    db.commit()
    r = c.put(URL, json=_lote(escenario, "2026-09", [{**reg, "compromiso_id": comp.id}]))
    assert r.status_code == 422
    # Todo o nada: nada quedó guardado
    assert c.get(URL, params={"presupuesto_id": escenario.presupuesto.id}).json() == []
    assert (
        c.get(URL, params={"presupuesto_id": escenario.presupuesto.id, "periodo": "2026-1"}).status_code
        == 422
    )
    assert c.get(URL, params={"presupuesto_id": 9999}).status_code == 404


def test_eliminar_y_roles(client_as, escenario: Escenario) -> None:
    c = client_as("obra")
    c.put(
        URL,
        json=_lote(
            escenario,
            "2026-09",
            [{"item_id": escenario.item_a.id, "valor_ejecutado": "1", "avance_fisico_pct": "0.1"}],
        ),
    )
    eid = c.get(URL, params={"presupuesto_id": escenario.presupuesto.id}).json()[0]["id"]
    consulta = client_as("consulta")
    assert consulta.delete(f"{URL}/{eid}").status_code == 403
    assert (
        consulta.put(
            URL,
            json=_lote(
                escenario,
                "2026-09",
                [{"item_id": escenario.item_a.id, "valor_ejecutado": "1", "avance_fisico_pct": "0.1"}],
            ),
        ).status_code
        == 403
    )
    r = c.delete(f"{URL}/{eid}")
    assert r.status_code == 204 and r.content == b""
    assert c.delete(f"{URL}/{eid}").status_code == 404
