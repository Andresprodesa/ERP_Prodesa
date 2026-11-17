"""Tests del submódulo APU: composición, reglas, valorización (ejemplos calculados a mano) y roles."""

from __future__ import annotations

from decimal import Decimal

from app.core.models import AuditLog
from app.modules.adpro.apu.service import insumos_duplicados, subtotales_por_tipo
from app.modules.adpro.enums import TipoInsumo

D = Decimal
URL = "/api/adpro/apu/apus"


# --- Funciones puras ---------------------------------------------------------------------
def test_subtotales_por_tipo_incluye_todos_los_tipos() -> None:
    r = subtotales_por_tipo(
        [(TipoInsumo.MAT, D("2100")), (TipoInsumo.MO, D("10000")), (TipoInsumo.MAT, D("0.00004"))]
    )
    assert r == {"MAT": D("2100.0000"), "MO": D("10000.0000"), "EQ": D("0"), "TR": D("0"), "SUB": D("0")}


def test_insumos_duplicados() -> None:
    assert insumos_duplicados([1, 2, 3]) == []
    assert insumos_duplicados([1, 2, 1, 3, 2, 1]) == [1, 2]


# --- Consulta ----------------------------------------------------------------------------
def test_obtener_y_por_item(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    r = auth_client.get(f"{URL}/{esc['apu_muro']}")
    assert r.status_code == 200
    body = r.json()
    assert body["item_codigo"] == "01.01.001.0001" and body["unidad_codigo"] == "M2"
    assert body["num_insumos"] == 2
    assert [c["insumo_codigo"] for c in body["insumos"]] == ["MAT-001", "MO-001"]
    assert D(body["insumos"][0]["desperdicio_pct"]) == D("0.05")
    assert body["created_by"] == "tester"

    r = auth_client.get(f"{URL}/por-item/{esc['concreto']}")
    assert r.status_code == 200 and r.json()["id"] == esc["apu_concreto"]
    r = auth_client.get(f"{URL}/por-item/{esc['losa']}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_listar_con_filtros(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    r = auth_client.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and [a["item_codigo"] for a in body["items"]] == [
        "01.01.001.0001",
        "01.01.001.0002",
    ]
    assert auth_client.get(URL, params={"q": "concreto"}).json()["total"] == 1
    assert auth_client.get(URL, params={"capitulo_id": esc["cap01"]}).json()["total"] == 2
    assert auth_client.get(URL, params={"capitulo_id": esc["cap02"]}).json()["total"] == 0
    p = auth_client.get(URL, params={"limit": 1, "offset": 1}).json()
    assert p["total"] == 2 and len(p["items"]) == 1 and p["items"][0]["item_codigo"] == "01.01.001.0002"


# --- Creación y reglas -------------------------------------------------------------------
def test_crear_apu_y_reglas(auth_client, esc, db) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "item_id": esc["panete"],
        "insumos": [
            {"insumo_id": esc["cem"], "cantidad": "4.123456", "desperdicio_pct": "0.025"},
            {"insumo_id": esc["mo"], "cantidad": "0.25"},
        ],
    }
    r = auth_client.post(URL, json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["descripcion"] == "Pañete liso (demo)"  # por defecto, la del ítem
    assert [c["orden"] for c in body["insumos"]] == [1, 2]
    assert D(body["insumos"][1]["desperdicio_pct"]) == D("0")
    assert db.query(AuditLog).filter_by(entidad="apu", accion="CREAR").count() == 1

    # el ítem ya tiene APU -> 409
    assert auth_client.post(URL, json={"item_id": esc["panete"]}).status_code == 409
    # nodo que no es ITEM -> 422 BUSINESS_RULE
    r = auth_client.post(URL, json={"item_id": esc["grupo01"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    # ítem inexistente -> 404
    assert auth_client.post(URL, json={"item_id": 99999}).status_code == 404


def test_crear_apu_insumo_repetido_inactivo_y_decimales(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    rep = {
        "item_id": esc["losa"],
        "insumos": [{"insumo_id": esc["cem"], "cantidad": "1"}, {"insumo_id": esc["cem"], "cantidad": "2"}],
    }
    assert auth_client.post(URL, json=rep).status_code == 409
    ina = {"item_id": esc["losa"], "insumos": [{"insumo_id": esc["ina"], "cantidad": "1"}]}
    r = auth_client.post(URL, json=ina)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    # más de 6 decimales en la cantidad -> VALIDATION_ERROR
    dec = {"item_id": esc["losa"], "insumos": [{"insumo_id": esc["cem"], "cantidad": "1.1234567"}]}
    r = auth_client.post(URL, json=dec)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    neg = {"item_id": esc["losa"], "insumos": [{"insumo_id": esc["cem"], "cantidad": "-1"}]}
    assert auth_client.post(URL, json=neg).status_code == 422
    # nada se creó
    assert auth_client.get(f"{URL}/por-item/{esc['losa']}").status_code == 404


def test_agregar_editar_quitar_insumo(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    base = f"{URL}/{esc['apu_muro']}/insumos"
    r = auth_client.post(base, json={"insumo_id": esc["eq"], "cantidad": "0.1", "desperdicio_pct": "0"})
    assert r.status_code == 201
    comp = r.json()
    assert comp["insumo_codigo"] == "EQ-001" and comp["tipo"] == "EQ" and comp["orden"] == 3
    # repetido -> 409
    assert auth_client.post(base, json={"insumo_id": esc["eq"], "cantidad": "1"}).status_code == 409
    # editar
    r = auth_client.put(
        f"{base}/{comp['id']}", json={"cantidad": "0.2", "observacion": "rendimiento ajustado"}
    )
    assert r.status_code == 200 and D(r.json()["cantidad"]) == D("0.2")
    assert r.json()["observacion"] == "rendimiento ajustado"
    # componente de otro APU -> 404
    assert (
        auth_client.put(
            f"{URL}/{esc['apu_concreto']}/insumos/{comp['id']}", json={"cantidad": "1"}
        ).status_code
        == 404
    )
    # quitar
    assert auth_client.delete(f"{base}/{comp['id']}").status_code == 204
    assert auth_client.get(f"{URL}/{esc['apu_muro']}").json()["num_insumos"] == 2


def test_reemplazar_composicion_y_actualizar_cabecera(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    r = auth_client.put(
        f"{URL}/{esc['apu_muro']}/insumos",
        json={
            "insumos": [
                {"insumo_id": esc["mo"], "cantidad": "0.75"},
                {"insumo_id": esc["cem"], "cantidad": "3"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert [(c["insumo_codigo"], D(c["cantidad"])) for c in r.json()["insumos"]] == [
        ("MO-001", D("0.75")),
        ("MAT-001", D("3")),
    ]
    r = auth_client.put(f"{URL}/{esc['apu_muro']}", json={"descripcion": "Muro v2", "activo": False})
    assert r.status_code == 200 and r.json()["descripcion"] == "Muro v2" and r.json()["activo"] is False
    assert auth_client.get(URL, params={"activo": "false"}).json()["total"] == 1


def test_copiar_apu(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    r = auth_client.post(f"{URL}/{esc['apu_concreto']}/copiar", json={"item_id_destino": esc["losa"]})
    assert r.status_code == 201
    body = r.json()
    assert body["item_id"] == esc["losa"] and body["num_insumos"] == 3
    assert body["descripcion"] == "APU concreto demo"
    # destino que ya tiene APU -> 409
    r = auth_client.post(f"{URL}/{esc['apu_concreto']}/copiar", json={"item_id_destino": esc["muro"]})
    assert r.status_code == 409


# --- Valorización (calculada a mano) -------------------------------------------------------
def test_valorizacion_con_desperdicio_y_vigencia(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    url = f"{URL}/{esc['apu_concreto']}/valorizacion"
    r = auth_client.get(url, params={"ciudad_id": esc["bog"], "fecha": "2026-03-01"})
    assert r.status_code == 200
    v = r.json()
    # 350·1.03·1000 = 360500 ; 0.55·1.10·50000 = 30250 ; 0.333333·8000 = 2666.664
    assert D(v["valor_unitario"]) == D("393416.6640")
    comps = {c["insumo_codigo"]: c for c in v["componentes"]}
    assert D(comps["MAT-001"]["valor_unitario"]) == D("360500")
    assert D(comps["MAT-002"]["valor_unitario"]) == D("30250")
    assert D(comps["EQ-001"]["valor_unitario"]) == D("2666.664")
    assert comps["MAT-001"]["lista_id"] == esc["l1"]
    sub = {k: D(x) for k, x in v["subtotales_por_tipo"].items()}
    assert sub == {"MAT": D("390750"), "MO": D("0"), "EQ": D("2666.664"), "TR": D("0"), "SUB": D("0")}
    assert v["insumos_sin_precio"] == []

    # Agosto: el cemento sube a 1200 (lista L2): 350·1.03·1200 = 432600
    v2 = auth_client.get(url, params={"ciudad_id": esc["bog"], "fecha": "2026-08-01"}).json()
    assert D(v2["valor_unitario"]) == D("465516.6640")
    assert {c["insumo_codigo"]: c["lista_id"] for c in v2["componentes"]}["MAT-001"] == esc["l2"]


def test_valorizacion_con_precio_faltante(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "item_id": esc["panete"],
        "insumos": [
            {"insumo_id": esc["cem"], "cantidad": "4.123456", "desperdicio_pct": "0.025"},
            {"insumo_id": esc["mo"], "cantidad": "0.25"},
            {"insumo_id": esc["sub"], "cantidad": "1"},
        ],
    }
    apu_id = auth_client.post(URL, json=payload).json()["id"]
    v = auth_client.get(
        f"{URL}/{apu_id}/valorizacion", params={"ciudad_id": esc["bog"], "fecha": "2026-03-01"}
    ).json()
    # 4.123456·1.025·1000 = 4226.5424 (q4) ; 0.25·20000 = 5000 ; SUB sin precio aporta 0
    assert D(v["valor_unitario"]) == D("9226.5424")
    assert v["insumos_sin_precio"] == [esc["sub"]]
    sub = [c for c in v["componentes"] if c["insumo_id"] == esc["sub"]][0]
    assert sub["precio_faltante"] is True and D(sub["precio_unitario"]) == 0 and sub["lista_id"] is None
    # Medellín no tiene listas: todo sin precio
    v = auth_client.get(
        f"{URL}/{apu_id}/valorizacion", params={"ciudad_id": esc["mde"], "fecha": "2026-03-01"}
    ).json()
    assert D(v["valor_unitario"]) == 0 and len(v["insumos_sin_precio"]) == 3
    # ciudad inexistente -> 404 ; ciudad obligatoria -> 422
    assert auth_client.get(f"{URL}/{apu_id}/valorizacion", params={"ciudad_id": 999}).status_code == 404
    assert auth_client.get(f"{URL}/{apu_id}/valorizacion").status_code == 422


# --- Roles -------------------------------------------------------------------------------
def test_roles(client_as, esc, client) -> None:  # type: ignore[no-untyped-def]
    assert client.get(URL).status_code == 401
    consulta = client_as("consulta")
    assert consulta.get(URL).status_code == 200
    r = consulta.post(URL, json={"item_id": esc["losa"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    obra = client_as("obra")
    assert obra.delete(f"{URL}/{esc['apu_muro']}/insumos/1").status_code == 403
    presupuesto = client_as("presupuesto")
    assert presupuesto.post(URL, json={"item_id": esc["losa"]}).status_code == 201
