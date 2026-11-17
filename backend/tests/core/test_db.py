"""Tipos de columna del núcleo: fechas con hora siempre en UTC con zona (SQLite y PostgreSQL)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.audit import registrar_auditoria
from app.core.models import AuditLog, Rol, Usuario


def test_fechas_se_leen_en_utc_con_zona(db: Session) -> None:
    bogota = timezone(timedelta(hours=-5))
    u = Usuario(username="tz", nombre="Usuario zona (demo)", rol=Rol.CONSULTA)
    db.add(u)
    log = registrar_auditoria(db, accion="CREAR", entidad="prueba", entidad_id=1)
    log.timestamp = datetime(2026, 11, 17, 7, 0, tzinfo=bogota)
    db.commit()
    db.expire_all()

    u2 = db.get(Usuario, u.id)
    log2 = db.get(AuditLog, log.id)
    assert u2 is not None and log2 is not None
    assert u2.created_at.tzinfo is not None and u2.created_at.utcoffset() == timedelta(0)
    assert log2.timestamp == datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    assert log2.timestamp.isoformat().endswith("+00:00")
