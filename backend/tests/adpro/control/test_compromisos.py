"""Compromisos (§5.2): CRUD, reglas de estado, advertencias, roles y auditoría."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.core.models import AuditLog
from tests.adpro.control.conftest import Escenario

D = Decimal
URL = "/api/adpro/control/compromisos"


def _payload(esc: Escenario, numero: str = "OC-001", **kw):  # type: ignore[no-untyped-def]
    base = {
        "presupuesto_id": esc.presupuesto.id,
        "tipo": "ORDEN_COMPRA",
        "numero": numero,
        "fecha": "2026-09-15",
        "tercero": "Proveedor Demo S.A.S.",
        "descripcion": "Suministro demo",
        "lineas": [
            {
                "item_id": esc.item_a.id,
                "insumo_id": esc.cemento.id,
                "cantidad": "60",
                "valor_unitario": "12000",
            },
            {"item_id": esc.item_c.id, "cantidad": "1", "valor_unitario": "650000.5"},
        ],
    }
    base.update(kw)
    return base


def test_crear_compromiso_totales_y_advertencias(client_as, escenario: Escenario, db) -> None:
    c = client_as("obra")
    r = c.post(URL, json=_payload(escenario))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["estado"] == "VIGENTE" and body["num_lineas"] == 2
    # 60*12000 = 720000 ; 1*650000.5 = 650001 (redondeo a pesos HALF_UP)
    assert D(body["valor_total"]) == D("1370001")
    lineas = {ln["item_codigo"]: ln for ln in body["lineas"]}
    assert D(lineas["02.01.001.0001"]["valor_total"]) == D("650001")
    assert lineas["01.01.001.0001"]["insumo_codigo"] == "MAT-001"
    # Ítem C presupuestado en 600.000 en la versión CONTROL -> se excede
    assert any("02.01.001.0001" in a and "supera" in a for a in body["advertencias"])
    assert body["created_by"].startswith("test_obra")
    log = db.scalars(select(AuditLog).where(AuditLog.entidad == "compromiso")).all()
    assert [x.accion for x in log] == ["CREAR"]


def test_advertencia_item_fuera_de_version(client_as, escenario: Escenario) -> None:
    c = client_as("admin")
    p = _payload(
        escenario, lineas=[{"item_id": escenario.item_d.id, "cantidad": "1", "valor_unitario": "10"}]
    )
    r = c.post(URL, json=p)
    assert r.status_code == 201
    assert any("no está en la versión de control" in a for a in r.json()["advertencias"])


def test_compromiso_duplicado_y_validaciones(client_as, escenario: Escenario) -> None:
    c = client_as("presupuesto")
    assert c.post(URL, json=_payload(escenario)).status_code == 201
    r = c.post(URL, json=_payload(escenario))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    # mismo número, distinto tipo: permitido
    assert c.post(URL, json=_payload(escenario, tipo="CONTRATO")).status_code == 201
    # ítem que no es nivel ITEM
    r = c.post(
        URL,
        json=_payload(
            escenario,
            numero="X1",
            lineas=[{"item_id": escenario.cap1.id, "cantidad": "1", "valor_unitario": "1"}],
        ),
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    # sin líneas / cantidad negativa -> validación de esquema
    assert c.post(URL, json=_payload(escenario, numero="X2", lineas=[])).status_code == 422
    r = c.post(
        URL,
        json=_payload(
            escenario,
            numero="X3",
            lineas=[{"item_id": escenario.item_a.id, "cantidad": "-1", "valor_unitario": "1"}],
        ),
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    # presupuesto inexistente
    assert c.post(URL, json=_payload(escenario, numero="X4", presupuesto_id=9999)).status_code == 404


def test_roles_compromisos(client_as, escenario: Escenario) -> None:
    r = client_as("consulta").post(URL, json=_payload(escenario))
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert client_as("consulta").get(URL).status_code == 200


def test_listar_y_filtrar(client_as, escenario: Escenario) -> None:
    c = client_as("admin")
    c.post(URL, json=_payload(escenario, numero="OC-001"))
    c.post(
        URL,
        json=_payload(
            escenario,
            numero="CT-777",
            tipo="CONTRATO",
            tercero="Contratista Ficticio Ltda",
            lineas=[{"item_id": escenario.item_b.id, "cantidad": "1", "valor_unitario": "100"}],
        ),
    )
    r = c.get(URL, params={"presupuesto_id": escenario.presupuesto.id})
    assert r.status_code == 200 and r.json()["total"] == 2
    assert r.json()["items"][0]["num_lineas"] >= 1
    assert c.get(URL, params={"tipo": "CONTRATO"}).json()["total"] == 1
    assert c.get(URL, params={"q": "ficticio"}).json()["items"][0]["numero"] == "CT-777"
    assert c.get(URL, params={"item_id": escenario.item_c.id}).json()["total"] == 1
    assert c.get(URL, params={"estado": "ANULADO"}).json()["total"] == 0
    page = c.get(URL, params={"limit": 1, "offset": 1}).json()
    assert len(page["items"]) == 1 and page["limit"] == 1 and page["offset"] == 1


def test_actualizar_reemplaza_lineas(client_as, escenario: Escenario) -> None:
    c = client_as("admin")
    cid = c.post(URL, json=_payload(escenario)).json()["id"]
    r = c.put(
        f"{URL}/{cid}",
        json={
            "tercero": "Otro Proveedor Demo",
            "lineas": [{"item_id": escenario.item_b.id, "cantidad": "2", "valor_unitario": "1000"}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tercero"] == "Otro Proveedor Demo" and body["num_lineas"] == 1
    assert D(body["valor_total"]) == D("2000") and body["advertencias"] == []
    # sin lineas: no las toca
    r = c.put(f"{URL}/{cid}", json={"descripcion": "Cambio"})
    assert r.json()["num_lineas"] == 1 and r.json()["descripcion"] == "Cambio"
    # numero duplicado al actualizar
    c.post(URL, json=_payload(escenario, numero="OC-002"))
    assert c.put(f"{URL}/{cid}", json={"numero": "OC-002"}).status_code == 409
    assert c.get(f"{URL}/{cid}").json()["numero"] == "OC-001"
    assert c.get(f"{URL}/99999").status_code == 404


def test_anular_y_liquidar(client_as, escenario: Escenario, db) -> None:
    c = client_as("obra")
    cid = c.post(URL, json=_payload(escenario)).json()["id"]
    r = c.post(f"{URL}/{cid}/anular", json={"motivo": "Error de digitación"})
    assert r.status_code == 200 and r.json()["estado"] == "ANULADO" and r.json()["advertencias"] == []
    # ya no es editable
    r = c.put(f"{URL}/{cid}", json={"descripcion": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    assert c.post(f"{URL}/{cid}/liquidar", json={}).status_code == 422
    assert c.post(f"{URL}/{cid}/anular", json={}).status_code == 422  # motivo obligatorio

    cid2 = c.post(URL, json=_payload(escenario, numero="OC-009")).json()["id"]
    r = c.post(f"{URL}/{cid2}/liquidar", json={})
    assert r.status_code == 200 and r.json()["estado"] == "LIQUIDADO"
    acciones = db.scalars(select(AuditLog.accion).where(AuditLog.entidad == "compromiso")).all()
    assert "ANULAR" in acciones and acciones.count("CREAR") == 2


def test_compromiso_sin_version_aprobada(client_as, escenario: Escenario, db) -> None:
    from app.modules.adpro.models import Presupuesto

    p2 = Presupuesto(proyecto_id=escenario.proyecto.id, codigo="PPTO-02", nombre="Sin aprobar")
    db.add(p2)
    db.commit()
    r = client_as("admin").post(URL, json=_payload(escenario, presupuesto_id=p2.id))
    assert r.status_code == 201
    assert r.json()["advertencias"] == [
        "El presupuesto no tiene una versión APROBADA para validar el compromiso"
    ]
