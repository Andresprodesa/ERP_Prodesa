"""API de presupuestos, versiones, líneas, resumen (AIU) y explosión."""

from __future__ import annotations

from decimal import Decimal

from app.core.models import AuditLog

D = Decimal
BASE = "/api/adpro/presupuestos"


# --- Presupuestos ------------------------------------------------------------------------
def test_crear_listar_actualizar_presupuesto(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    r = auth_client.post(
        BASE,
        json={
            "proyecto_id": esc["proyecto"],
            "etapa_id": esc["etapa"],
            "codigo": " ppto-01 ",
            "nombre": "Demo",
        },
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["codigo"] == "PPTO-01" and p["proyecto_codigo"] == "PRY-DEMO-01" and p["etapa_codigo"] == "E1"
    assert p["num_versiones"] == 0 and p["versiones"] == []
    # duplicado en el mismo proyecto -> 409
    assert (
        auth_client.post(
            BASE, json={"proyecto_id": esc["proyecto"], "codigo": "PPTO-01", "nombre": "x"}
        ).status_code
        == 409
    )
    # etapa de otro proyecto -> 422
    r = auth_client.post(
        BASE,
        json={"proyecto_id": esc["proyecto"], "etapa_id": esc["etapa_otro"], "codigo": "X", "nombre": "x"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    assert auth_client.post(BASE, json={"proyecto_id": 999, "codigo": "X", "nombre": "x"}).status_code == 404

    assert len(auth_client.get(BASE).json()) == 1
    assert auth_client.get(BASE, params={"proyecto_id": esc["proyecto2"]}).json() == []
    assert len(auth_client.get(BASE, params={"q": "demo"}).json()) == 1

    r = auth_client.put(f"{BASE}/{p['id']}", json={"nombre": "Nuevo nombre", "descripcion": "desc"})
    assert r.status_code == 200 and r.json()["nombre"] == "Nuevo nombre"
    assert auth_client.get(f"{BASE}/999").status_code == 404


# --- Versiones ---------------------------------------------------------------------------
def test_crear_version_numeracion_y_defaults(auth_client, esc, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1(con_lineas=False)
    v1 = auth_client.get(f"{BASE}/versiones/{ids['vid']}").json()
    assert v1["numero"] == 1 and v1["estado"] == "BORRADOR" and v1["editable"] is True
    assert (
        v1["ciudad_precios_id"] == esc["bog"] and v1["ciudad_precios_codigo"] == "BOG"
    )  # ciudad del proyecto
    r = auth_client.post(
        f"{BASE}/{ids['pid']}/versiones",
        json={"tipo": "FIV", "nombre": "FIV", "fecha_precios": "2026-08-01", "ciudad_precios_id": esc["mde"]},
    )
    assert r.status_code == 201
    v2 = r.json()
    assert v2["numero"] == 2 and v2["ciudad_precios_codigo"] == "MDE"
    assert D(v2["iva_utilidad_pct"]) == D("0.19") and D(v2["administracion_pct"]) == 0
    # porcentaje fuera de rango -> 422
    r = auth_client.post(
        f"{BASE}/{ids['pid']}/versiones",
        json={"tipo": "OTRO", "nombre": "x", "fecha_precios": "2026-08-01", "utilidad_pct": "1.5"},
    )
    assert r.status_code == 422
    det = auth_client.get(f"{BASE}/{ids['pid']}").json()
    assert det["num_versiones"] == 2 and [v["numero"] for v in det["versiones"]] == [1, 2]


def test_actualizar_y_eliminar_version_borrador(auth_client, crear_v1, db) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    r = auth_client.put(
        f"{BASE}/versiones/{ids['vid']}", json={"utilidad_pct": "0.10", "nombre": "FIC ajustada"}
    )
    assert r.status_code == 200
    assert D(r.json()["utilidad_pct"]) == D("0.10") and r.json()["nombre"] == "FIC ajustada"
    # CD 6355248 ; A 508420 ; I 127105 ; U 635525 (635524.8) ; IVA 120750 (120749.75) -> 7747048
    assert D(r.json()["total_presupuesto"]) == D("7747048")
    assert auth_client.delete(f"{BASE}/versiones/{ids['vid']}").status_code == 204
    assert auth_client.get(f"{BASE}/versiones/{ids['vid']}").status_code == 404
    assert db.query(AuditLog).filter_by(entidad="presupuesto_version", accion="ELIMINAR").count() == 1


# --- Líneas ------------------------------------------------------------------------------
def test_lineas_valorizadas_desde_apu_y_manual(auth_client, esc, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    lineas = auth_client.get(f"{BASE}/versiones/{ids['vid']}/lineas").json()
    assert [ln["item_codigo"] for ln in lineas] == ["01.01.001.0001", "01.01.001.0002", "02.01.001.0001"]
    muro, conc, losa = lineas
    assert (D(muro["valor_unitario"]), D(muro["valor_total"])) == (D("12100"), D("1216050"))
    assert muro["origen_unitario"] == "APU" and muro["num_insumos"] == 2 and muro["insumos_sin_precio"] == []
    assert muro["capitulo_codigo"] == "01" and muro["unidad_codigo"] == "M2"
    assert (D(conc["valor_unitario"]), D(conc["valor_total"])) == (D("393416.664"), D("4858696"))
    assert losa["origen_unitario"] == "MANUAL" and losa["num_insumos"] == 0
    assert D(losa["valor_total"]) == D("280502") and losa["capitulo_id"] == esc["cap02"]

    # filtros
    assert (
        len(
            auth_client.get(
                f"{BASE}/versiones/{ids['vid']}/lineas", params={"capitulo_id": esc["cap02"]}
            ).json()
        )
        == 1
    )
    assert len(auth_client.get(f"{BASE}/versiones/{ids['vid']}/lineas", params={"q": "concreto"}).json()) == 1

    # snapshot de la composición del concreto
    ins = auth_client.get(f"{BASE}/versiones/{ids['vid']}/lineas/{conc['id']}/insumos").json()
    por_cod = {i["insumo_codigo"]: i for i in ins}
    assert D(por_cod["MAT-002"]["cantidad_total"]) == D("7.4718")  # 12.35·0.55·1.10 = 7.47175
    assert D(por_cod["MAT-002"]["valor_total"]) == D("373590")
    assert D(por_cod["MAT-001"]["cantidad_unitaria"]) == D("350") and D(
        por_cod["MAT-001"]["desperdicio_pct"]
    ) == D("0.03")


def test_reglas_de_lineas(auth_client, esc, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    url = f"{BASE}/versiones/{ids['vid']}/lineas"
    # ítem repetido -> 409
    assert auth_client.post(url, json={"item_id": esc["muro"], "cantidad": "1"}).status_code == 409
    # ítem sin APU y sin valor -> 422
    r = auth_client.post(url, json={"item_id": esc["panete"], "cantidad": "1"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    # nodo no ITEM -> 422 ; inexistente -> 404
    assert (
        auth_client.post(
            url, json={"item_id": esc["grupo01"], "cantidad": "1", "valor_unitario": "1"}
        ).status_code
        == 422
    )
    assert auth_client.post(url, json={"item_id": 9999, "cantidad": "1"}).status_code == 404
    # manual con redondeo half-up: 3 × 0.5 = 1.5 -> 2
    r = auth_client.post(url, json={"item_id": esc["panete"], "cantidad": "3", "valor_unitario": "0.5"})
    assert r.status_code == 201 and D(r.json()["valor_total"]) == D("2")
    # lote todo o nada: una línea mala -> nada se crea
    r = auth_client.post(
        f"{url}/lote",
        json={
            "lineas": [
                {"item_id": esc["panete"], "cantidad": "1", "valor_unitario": "1"},
                {"item_id": 9999, "cantidad": "1"},
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["creadas"] == 0 and [e["indice"] for e in body["errores"]] == [0, 1]
    assert len(auth_client.get(url).json()) == 4


def test_actualizar_y_eliminar_linea(auth_client, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    url = f"{BASE}/versiones/{ids['vid']}/lineas"
    muro = auth_client.get(url).json()[0]
    # cambiar cantidad conserva el unitario APU y el snapshot: 200 × 12100
    r = auth_client.put(f"{url}/{muro['id']}", json={"cantidad": "200"})
    assert (
        r.status_code == 200 and D(r.json()["valor_total"]) == D("2420000") and r.json()["num_insumos"] == 2
    )
    # enviar valor_unitario la vuelve MANUAL y borra el snapshot
    r = auth_client.put(
        f"{url}/{muro['id']}", json={"valor_unitario": "10000.25", "observacion": "negociado"}
    )
    body = r.json()
    assert (
        body["origen_unitario"] == "MANUAL"
        and body["num_insumos"] == 0
        and D(body["valor_total"]) == D("2000050")
    )
    assert auth_client.delete(f"{url}/{muro['id']}").status_code == 204
    assert len(auth_client.get(url).json()) == 2
    assert auth_client.delete(f"{url}/{muro['id']}").status_code == 404


# --- Resumen (AIU) y explosión ---------------------------------------------------------------
def test_resumen_aiu_por_capitulo(auth_client, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    r = auth_client.get(f"{BASE}/versiones/{ids['vid']}/resumen").json()
    assert D(r["costo_directo"]) == D("6355248")
    assert (D(r["administracion"]), D(r["imprevistos"]), D(r["utilidad"])) == (
        D("508420"),
        D("127105"),
        D("317762"),
    )
    assert D(r["iva_utilidad"]) == D("60375") and D(r["total_aiu"]) == D("953287")
    assert D(r["total"]) == D("7368910")
    assert r["num_lineas"] == 3 and r["lineas_sin_precio"] == 0
    caps = {c["codigo"]: c for c in r["capitulos"]}
    assert D(caps["01"]["valor"]) == D("6074746") and caps["01"]["num_lineas"] == 2
    assert D(caps["01"]["participacion_pct"]) == D("0.955863")
    assert D(caps["02"]["valor"]) == D("280502") and D(caps["02"]["participacion_pct"]) == D("0.044137")
    v = auth_client.get(f"{BASE}/versiones/{ids['vid']}").json()
    assert D(v["total_costo_directo"]) == D("6355248") and D(v["total_presupuesto"]) == D("7368910")
    assert v["num_lineas"] == 3


def test_explosion_por_insumo_y_tipo(auth_client, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    e = auth_client.get(f"{BASE}/versiones/{ids['vid']}/explosion").json()
    filas = {f["insumo_codigo"]: f for f in e["filas"]}
    assert list(filas) == ["EQ-001", "MAT-001", "MAT-002", "MO-001"]
    assert (D(filas["MAT-001"]["cantidad_total"]), D(filas["MAT-001"]["valor_total"])) == (
        D("4663.225"),
        D("4663225"),
    )
    assert (D(filas["MAT-002"]["cantidad_total"]), D(filas["MAT-002"]["valor_total"])) == (
        D("7.4718"),
        D("373590"),
    )
    assert (D(filas["EQ-001"]["cantidad_total"]), D(filas["EQ-001"]["valor_total"])) == (
        D("4.1167"),
        D("32934"),
    )
    assert (D(filas["MO-001"]["cantidad_total"]), D(filas["MO-001"]["valor_total"])) == (
        D("50.25"),
        D("1005000"),
    )
    assert D(e["total_insumos"]) == D("6074749")  # vs 6074746 del capítulo: redondeo por insumo
    assert D(e["valor_sin_desglose"]) == D("280502")  # línea MANUAL de la losa
    assert D(e["total"]) == D("6355251")
    tipos = {t["tipo"]: t for t in e["por_tipo"]}
    assert [t["tipo"] for t in e["por_tipo"]] == ["MAT", "MO", "EQ"]
    assert D(tipos["MAT"]["valor_total"]) == D("5036815") and D(tipos["MAT"]["participacion_pct"]) == D(
        "0.829140"
    )
    assert D(tipos["MO"]["participacion_pct"]) == D("0.165439")

    solo_mat = auth_client.get(f"{BASE}/versiones/{ids['vid']}/explosion", params={"tipo": "MAT"}).json()
    assert [f["insumo_codigo"] for f in solo_mat["filas"]] == ["MAT-001", "MAT-002"]
    assert D(solo_mat["total_insumos"]) == D("5036815")
    assert D(solo_mat["filas"][0]["participacion_pct"]) == D(
        "0.925828"
    )  # 4663225 / 5036815 = 0.9258281 -> 0.925828


def test_roles_presupuesto(client_as, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    consulta = client_as("consulta")
    assert consulta.get(f"{BASE}/versiones/{ids['vid']}/resumen").status_code == 200
    assert consulta.post(BASE, json={"proyecto_id": 1, "codigo": "X", "nombre": "x"}).status_code == 403
    obra = client_as("obra")
    assert obra.put(f"{BASE}/versiones/{ids['vid']}", json={"nombre": "x"}).status_code == 403
    presupuesto = client_as("presupuesto")
    # solo admin aprueba
    r = presupuesto.post(f"{BASE}/versiones/{ids['vid']}/aprobar", json={})
    assert r.status_code == 403
