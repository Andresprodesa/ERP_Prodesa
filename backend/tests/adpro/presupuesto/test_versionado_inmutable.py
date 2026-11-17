"""Flujo BORRADOR -> APROBADO -> CERRADO, inmutabilidad (snapshot), copia, recálculo y auditoría."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import BusinessRuleError
from app.core.models import AuditLog
from app.modules.adpro.models import (
    ApuInsumo,
    ListaPrecios,
    PrecioInsumo,
    PresupuestoLinea,
    PresupuestoLineaInsumo,
    PresupuestoVersion,
)
from app.modules.adpro.presupuesto import schemas as ps
from app.modules.adpro.presupuesto import service

D = Decimal
BASE = "/api/adpro/presupuestos"


def _acciones(db, vid: int) -> list[str]:  # type: ignore[no-untyped-def]
    db.expire_all()
    return [
        a.accion
        for a in db.scalars(
            select(AuditLog)
            .where(AuditLog.entidad == "presupuesto_version", AuditLog.entidad_id == str(vid))
            .order_by(AuditLog.id)
        )
    ]


def test_aprobar_congela_totales_y_audita(auth_client, crear_v1, db) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    r = auth_client.post(f"{BASE}/versiones/{ids['vid']}/aprobar", json={"observacion": "Comité demo"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["estado"] == "APROBADO" and v["editable"] is False
    assert v["aprobado_por"].startswith("test_admin") and v["aprobado_at"] is not None
    assert D(v["total_costo_directo"]) == D("6355248") and D(v["total_presupuesto"]) == D("7368910")
    assert _acciones(db, ids["vid"]) == ["CREAR", "APROBAR"]
    log = db.scalars(select(AuditLog).where(AuditLog.accion == "APROBAR")).one()
    assert log.detalle["total_presupuesto"] == "7368910" and log.detalle["observacion"] == "Comité demo"
    # aprobar de nuevo -> 422
    assert auth_client.post(f"{BASE}/versiones/{ids['vid']}/aprobar", json={}).status_code == 422


def test_no_se_aprueba_sin_lineas(auth_client, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1(con_lineas=False)
    r = auth_client.post(f"{BASE}/versiones/{ids['vid']}/aprobar")
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    # cerrar exige APROBADO
    assert auth_client.post(f"{BASE}/versiones/{ids['vid']}/cerrar").status_code == 422


def test_version_aprobada_es_inmutable_por_api(auth_client, esc, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    vid = ids["vid"]
    auth_client.post(f"{BASE}/versiones/{vid}/aprobar")
    lineas = auth_client.get(f"{BASE}/versiones/{vid}/lineas").json()
    lid = lineas[0]["id"]
    intentos = [
        auth_client.put(f"{BASE}/versiones/{vid}", json={"nombre": "x"}),
        auth_client.delete(f"{BASE}/versiones/{vid}"),
        auth_client.post(f"{BASE}/versiones/{vid}/recalcular", json={}),
        auth_client.post(
            f"{BASE}/versiones/{vid}/lineas",
            json={"item_id": esc["panete"], "cantidad": "1", "valor_unitario": "1"},
        ),
        auth_client.post(
            f"{BASE}/versiones/{vid}/lineas/lote",
            json={"lineas": [{"item_id": esc["panete"], "cantidad": "1", "valor_unitario": "1"}]},
        ),
        auth_client.put(f"{BASE}/versiones/{vid}/lineas/{lid}", json={"cantidad": "1"}),
        auth_client.delete(f"{BASE}/versiones/{vid}/lineas/{lid}"),
    ]
    for r in intentos:
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "BUSINESS_RULE"
    assert auth_client.get(f"{BASE}/versiones/{vid}/lineas").json() == lineas


def test_snapshot_no_cambia_con_precios_ni_apu(auth_client, esc, crear_v1, db) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    vid = ids["vid"]
    auth_client.post(f"{BASE}/versiones/{vid}/aprobar")
    antes = auth_client.get(f"{BASE}/versiones/{vid}/resumen").json()
    explosion_antes = auth_client.get(f"{BASE}/versiones/{vid}/explosion").json()
    # nueva lista con el cemento al triple, vigente ANTES de la fecha de la versión, y APU modificado
    nueva = ListaPrecios(
        codigo="BOG-2026-02", nombre="BOG feb", ciudad_id=esc["bog"], fecha_desde=date(2026, 2, 1)
    )
    db.add(nueva)
    db.flush()
    db.add(PrecioInsumo(lista_id=nueva.id, insumo_id=esc["cem"], precio=D("3000")))
    comp = db.scalar(
        select(ApuInsumo).where(ApuInsumo.apu_id == esc["apu_muro"], ApuInsumo.insumo_id == esc["mo"])
    )
    comp.cantidad = D("5")
    db.commit()
    assert auth_client.get(f"{BASE}/versiones/{vid}/resumen").json() == antes
    assert auth_client.get(f"{BASE}/versiones/{vid}/explosion").json() == explosion_antes
    assert D(auth_client.get(f"{BASE}/versiones/{vid}").json()["total_presupuesto"]) == D("7368910")


def test_guardia_orm_bloquea_escrituras_directas(crear_v1, db) -> None:  # type: ignore[no-untyped-def]
    """Defensa en profundidad: aunque un service olvide asegurar_editable, el flush falla."""
    ids = crear_v1()
    service.aprobar_version(db, ids["vid"])
    linea = db.scalars(select(PresupuestoLinea).where(PresupuestoLinea.version_id == ids["vid"])).first()
    linea.cantidad = D("1")
    with pytest.raises(BusinessRuleError):
        db.flush()
    db.rollback()

    snap = db.scalars(
        select(PresupuestoLineaInsumo).where(PresupuestoLineaInsumo.linea_id == linea.id)
    ).first()
    snap.precio_unitario = D("1")
    with pytest.raises(BusinessRuleError):
        db.flush()
    db.rollback()

    v = db.get(PresupuestoVersion, ids["vid"])
    v.utilidad_pct = D("0.5")
    with pytest.raises(BusinessRuleError):
        db.flush()
    db.rollback()

    db.add(PresupuestoLinea(version_id=ids["vid"], item_id=linea.item_id + 1000, cantidad=D("1")))
    with pytest.raises(BusinessRuleError):
        db.flush()
    db.rollback()

    with pytest.raises(BusinessRuleError):
        service.aplicar_lineas(db, ids["vid"], [ps.LineaCreate(item_id=1, cantidad=D("1"))], modo="agregar")


def test_cerrar_y_cerrada_inmutable(auth_client, crear_v1, db) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    vid = ids["vid"]
    auth_client.post(f"{BASE}/versiones/{vid}/aprobar")
    r = auth_client.post(f"{BASE}/versiones/{vid}/cerrar", json={"observacion": "fin de obra demo"})
    assert r.status_code == 200 and r.json()["estado"] == "CERRADO" and r.json()["cerrado_por"]
    assert D(r.json()["total_presupuesto"]) == D("7368910")
    assert auth_client.post(f"{BASE}/versiones/{vid}/cerrar").status_code == 422
    assert auth_client.post(f"{BASE}/versiones/{vid}/aprobar").status_code == 422
    assert auth_client.put(f"{BASE}/versiones/{vid}", json={"nombre": "x"}).status_code == 422
    assert _acciones(db, vid) == ["CREAR", "APROBAR", "CERRAR"]
    # la guardia ORM tampoco permite reabrir la versión cerrada
    v = db.get(PresupuestoVersion, vid)
    v.estado = v.estado.__class__.BORRADOR
    with pytest.raises(BusinessRuleError):
        db.flush()
    db.rollback()


def test_copiar_version_sin_recalcular(auth_client, crear_v1, db) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    auth_client.post(f"{BASE}/versiones/{ids['vid']}/aprobar")
    r = auth_client.post(
        f"{BASE}/versiones/{ids['vid']}/copiar", json={"tipo": "CONTROL", "nombre": "Control 1"}
    )
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["numero"] == 2 and v2["estado"] == "BORRADOR" and v2["version_origen_id"] == ids["vid"]
    assert v2["tipo"] == "CONTROL" and D(v2["utilidad_pct"]) == D("0.05")
    assert D(v2["total_presupuesto"]) == D("7368910")
    l1 = auth_client.get(f"{BASE}/versiones/{ids['vid']}/lineas").json()
    l2 = auth_client.get(f"{BASE}/versiones/{v2['id']}/lineas").json()

    def clave(ls: list[dict]) -> list[tuple]:  # type: ignore[type-arg]
        return [
            (x["item_id"], x["valor_unitario"], x["valor_total"], x["num_insumos"], x["origen_unitario"])
            for x in ls
        ]

    assert clave(l1) == clave(l2)
    assert _acciones(db, v2["id"]) == ["COPIAR"]
    # la copia es editable
    assert (
        auth_client.put(
            f"{BASE}/versiones/{v2['id']}/lineas/{l2[0]['id']}", json={"cantidad": "1"}
        ).status_code
        == 200
    )


def test_copiar_version_revalorizando_y_a_otro_presupuesto(auth_client, esc, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    auth_client.post(f"{BASE}/versiones/{ids['vid']}/aprobar")
    otro = auth_client.post(
        BASE, json={"proyecto_id": esc["proyecto"], "codigo": "PPTO-02", "nombre": "Otro"}
    ).json()
    r = auth_client.post(
        f"{BASE}/versiones/{ids['vid']}/copiar",
        json={
            "tipo": "FIV",
            "nombre": "FIV agosto",
            "presupuesto_id_destino": otro["id"],
            "recalcular_precios": True,
            "fecha_precios": "2026-08-01",
        },
    )
    assert r.status_code == 201
    v = r.json()
    assert v["presupuesto_id"] == otro["id"] and v["numero"] == 1 and v["fecha_precios"] == "2026-08-01"
    # Muro 100.5 × 12520 = 1258260 ; Concreto 12.35 × 465516.664 = 5749130.8004 -> 5749131 ; Losa manual 280502
    assert D(v["total_costo_directo"]) == D("7287893")
    lineas = {x["item_codigo"]: x for x in auth_client.get(f"{BASE}/versiones/{v['id']}/lineas").json()}
    assert D(lineas["01.01.001.0001"]["valor_unitario"]) == D("12520")
    assert lineas["02.01.001.0001"]["origen_unitario"] == "MANUAL" and D(
        lineas["02.01.001.0001"]["valor_total"]
    ) == D("280502")
    # la versión origen no cambió
    assert D(auth_client.get(f"{BASE}/versiones/{ids['vid']}").json()["total_costo_directo"]) == D("6355248")


def test_recalcular_borrador_tras_cambio_de_apu(auth_client, esc, crear_v1, db) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    vid = ids["vid"]
    # sube la MO del muro a 0.6 HR y se mueve la fecha de precios a agosto
    comp = db.scalar(
        select(ApuInsumo).where(ApuInsumo.apu_id == esc["apu_muro"], ApuInsumo.insumo_id == esc["mo"])
    )
    comp.cantidad = D("0.6")
    db.commit()
    assert auth_client.put(f"{BASE}/versiones/{vid}", json={"fecha_precios": "2026-08-01"}).status_code == 200
    # cambiar la fecha NO recalcula por sí solo
    assert D(auth_client.get(f"{BASE}/versiones/{vid}").json()["total_costo_directo"]) == D("6355248")
    r = auth_client.post(f"{BASE}/versiones/{vid}/recalcular", json={})
    assert r.status_code == 200
    res = r.json()
    # Muro 2520 + 0.6·20000 = 14520 → 100.5 × 14520 = 1459260 ; Concreto 5749131 ; Losa 280502
    assert res["lineas_recalculadas"] == 2 and res["insumos_sin_precio"] == []
    assert D(res["total_costo_directo"]) == D("7488893")
    assert _acciones(db, vid)[-1] == "RECALCULAR"


def test_recalcular_reporta_insumos_sin_precio(auth_client, esc, crear_v1) -> None:  # type: ignore[no-untyped-def]
    ids = crear_v1()
    auth_client.post(
        f"/api/adpro/apu/apus/{esc['apu_muro']}/insumos", json={"insumo_id": esc["sub"], "cantidad": "1"}
    )
    res = auth_client.post(f"{BASE}/versiones/{ids['vid']}/recalcular").json()
    assert res["insumos_sin_precio"] == [esc["sub"]]
    resumen = auth_client.get(f"{BASE}/versiones/{ids['vid']}/resumen").json()
    assert resumen["lineas_sin_precio"] == 1
    muro = auth_client.get(f"{BASE}/versiones/{ids['vid']}/lineas").json()[0]
    assert muro["insumos_sin_precio"] == [esc["sub"]] and muro["num_insumos"] == 3


def test_aplicar_lineas_contrato_interno(crear_v1, esc, db) -> None:  # type: ignore[no-untyped-def]
    """Contrato §6 usado por la importación Excel de control."""
    ids = crear_v1()
    res = service.aplicar_lineas(
        db,
        ids["vid"],
        [
            ps.LineaCreate(item_id=esc["muro"], cantidad=D("10")),  # existente -> actualiza (APU)
            ps.LineaCreate(item_id=esc["panete"], cantidad=D("2"), valor_unitario=D("1000.5")),  # nueva
        ],
        modo="agregar",
        origen_manual=service.OrigenValor.IMPORTADO,
    )
    assert res == {"creadas": 1, "actualizadas": 1, "eliminadas": 0}
    lineas = {x.item_codigo: x for x in service.listar_lineas(db, ids["vid"])}
    assert lineas["01.01.001.0001"].valor_total == D("121000")
    assert lineas["02.01.001.0002"].origen_unitario.value == "IMPORTADO" and lineas[
        "02.01.001.0002"
    ].valor_total == D("2001")

    with pytest.raises(BusinessRuleError) as exc:
        service.aplicar_lineas(
            db,
            ids["vid"],
            [
                ps.LineaCreate(item_id=esc["losa"], cantidad=D("1")),
                ps.LineaCreate(item_id=esc["losa"], cantidad=D("1")),
            ],
            modo="reemplazar",
        )
    assert [d["indice"] for d in exc.value.details] == [0, 1]  # sin APU / repetido
    assert len(service.listar_lineas(db, ids["vid"])) == 4  # nada cambió

    res = service.aplicar_lineas(
        db, ids["vid"], [ps.LineaCreate(item_id=esc["concreto"], cantidad=D("1"))], modo="reemplazar"
    )
    assert res == {"creadas": 1, "actualizadas": 0, "eliminadas": 4}
    assert [x.item_codigo for x in service.listar_lineas(db, ids["vid"])] == ["01.01.001.0002"]
