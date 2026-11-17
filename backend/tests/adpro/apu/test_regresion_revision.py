"""Regresiones de la revisión en APU y maestros: auditoría de cambios que alteran el costo y
búsqueda de texto con comodines escapados. Datos 100 % sintéticos."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import AuditLog

APU = "/api/adpro/apu/apus"
MAESTROS = "/api/adpro/maestros"


def _logs(db: Session, entidad: str) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.entidad == entidad).order_by(AuditLog.id)))


def test_cambios_de_composicion_del_apu_quedan_auditados(auth_client, esc, db: Session) -> None:  # type: ignore[no-untyped-def]
    apu_id = esc["apu_muro"]
    antes = len(_logs(db, "apu"))
    r = auth_client.post(f"{APU}/{apu_id}/insumos", json={"insumo_id": esc["arena"], "cantidad": "0.1"})
    assert r.status_code == 201, r.text
    comp_id = r.json()["id"]
    assert auth_client.put(f"{APU}/{apu_id}/insumos/{comp_id}", json={"cantidad": "0.2"}).status_code == 200
    assert auth_client.delete(f"{APU}/{apu_id}/insumos/{comp_id}").status_code == 204
    assert auth_client.put(f"{APU}/{apu_id}", json={"activo": False}).status_code == 200
    nuevos = _logs(db, "apu")[antes:]
    ops = [(log.accion, (log.detalle or {}).get("operacion")) for log in nuevos]
    assert ops == [
        ("ACTUALIZAR", "agregar_insumo"),
        ("ACTUALIZAR", "actualizar_insumo"),
        ("ACTUALIZAR", "eliminar_insumo"),
        ("ACTUALIZAR", None),
    ]
    assert nuevos[1].detalle["cambios"]["cantidad"] == {"antes": "0.100000", "despues": "0.2"}
    assert nuevos[3].detalle["cambios"] == {"activo": {"antes": True, "despues": False}}
    assert all(log.entidad_id == str(apu_id) for log in nuevos)


def test_actualizar_insumo_del_maestro_queda_auditado(auth_client, esc, db: Session) -> None:  # type: ignore[no-untyped-def]
    r = auth_client.put(f"{MAESTROS}/insumos/{esc['arena']}", json={"descripcion": "Arena de peña (demo)"})
    assert r.status_code == 200, r.text
    log = _logs(db, "insumo")[-1]
    assert log.accion == "ACTUALIZAR" and log.entidad_id == str(esc["arena"])
    assert log.detalle["cambios"]["descripcion"]["despues"] == "Arena de peña (demo)"


def test_busqueda_escapa_comodines(auth_client, esc) -> None:  # type: ignore[no-untyped-def]
    # '_' y '%' son comodines de LIKE: sin escape coincidirían con todo
    assert auth_client.get(f"{MAESTROS}/insumos", params={"q": "_"}).json()["total"] == 0
    assert auth_client.get(f"{MAESTROS}/insumos", params={"q": "%"}).json()["total"] == 0
    assert auth_client.get(APU, params={"q": "_"}).json()["total"] == 0
    assert auth_client.get(f"{MAESTROS}/insumos", params={"q": "mat-00"}).json()["total"] >= 1
    assert auth_client.get(APU, params={"q": "MURO"}).json()["total"] >= 1
