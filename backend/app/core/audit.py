"""Registro en la bitácora de auditoría (``core_audit_log``).

Uso desde cualquier ``service.py`` (no hace commit; queda en la misma transacción):

    from app.core.audit import registrar_auditoria, Accion
    registrar_auditoria(db, accion=Accion.APROBAR, entidad="presupuesto_version",
                        entidad_id=version.id, detalle={"total": str(total)})

El usuario se toma de ``db.info`` (lo deja ``get_current_user``) salvo que se pase explícito.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SESSION_USER_KEY
from app.core.models import AuditLog

SESSION_USER_ID_KEY = "user_id"


class Accion(str, Enum):
    CREAR = "CREAR"
    ACTUALIZAR = "ACTUALIZAR"
    ELIMINAR = "ELIMINAR"
    APROBAR = "APROBAR"
    CERRAR = "CERRAR"
    COPIAR = "COPIAR"
    ANULAR = "ANULAR"
    IMPORTAR = "IMPORTAR"
    EXPORTAR = "EXPORTAR"
    RECALCULAR = "RECALCULAR"
    LOGIN = "LOGIN"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def registrar_auditoria(
    db: Session,
    *,
    accion: Accion | str,
    entidad: str,
    entidad_id: int | str | None = None,
    detalle: dict[str, Any] | None = None,
    username: str | None = None,
    usuario_id: int | None = None,
) -> AuditLog:
    log = AuditLog(
        usuario_id=usuario_id if usuario_id is not None else db.info.get(SESSION_USER_ID_KEY),
        username=username or db.info.get(SESSION_USER_KEY) or "sistema",
        accion=accion.value if isinstance(accion, Accion) else str(accion),
        entidad=entidad,
        entidad_id=None if entidad_id is None else str(entidad_id),
        detalle=_jsonable(detalle) if detalle is not None else None,
    )
    db.add(log)
    return log


def listar_auditoria(
    db: Session,
    *,
    entidad: str | None = None,
    entidad_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    from sqlalchemy import func

    stmt = select(AuditLog)
    if entidad:
        stmt = stmt.where(AuditLog.entidad == entidad)
    if entidad_id:
        stmt = stmt.where(AuditLog.entidad_id == entidad_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).all()
    return list(rows), int(total)
