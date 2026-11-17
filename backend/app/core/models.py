"""Modelos transversales del núcleo: usuarios y bitácora de auditoría."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UTCDateTime, str_enum, utcnow


class Rol(str, enum.Enum):
    """Roles del prototipo. En producción se mapean 1:1 a App Roles de Microsoft Entra ID."""

    ADMIN = "admin"
    PRESUPUESTO = "presupuesto"
    OBRA = "obra"
    CONSULTA = "consulta"


class Usuario(TimestampMixin, Base):
    __tablename__ = "core_usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    # Nulo para usuarios federados (Entra ID) que no tienen contraseña local.
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    rol: Mapped[Rol] = mapped_column(str_enum(Rol), nullable=False, default=Rol.CONSULTA)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Identificador externo (oid de Entra ID) para la migración a SSO.
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True)


class AuditLog(Base):
    """Bitácora inmutable de operaciones relevantes (cambios de estado, importaciones, etc.)."""

    __tablename__ = "core_audit_log"
    __table_args__ = (
        Index("ix_core_audit_log_entidad", "entidad", "entidad_id"),
        Index("ix_core_audit_log_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("core_usuario.id", ondelete="SET NULL"))
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    accion: Mapped[str] = mapped_column(String(50), nullable=False)  # p. ej. CREAR, APROBAR, IMPORTAR
    entidad: Mapped[str] = mapped_column(String(100), nullable=False)  # p. ej. presupuesto_version
    entidad_id: Mapped[str | None] = mapped_column(String(50))
    detalle: Mapped[dict[str, Any] | None] = mapped_column(JSON)
