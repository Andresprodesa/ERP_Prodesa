"""Motor, sesión y Base declarativa de SQLAlchemy 2.x.

Reglas:
- Código agnóstico del motor (SQLite en local, PostgreSQL en prod-like/producción).
- Convención de nombres de restricciones para que Alembic genere migraciones estables.
- Tipos numéricos estándar: ``Money`` y ``Qty`` (Numeric(18,4)), ``Coef`` (Numeric(18,6)) y
  ``Pct`` (Numeric(9,6), FRACCIÓN: 0.05 = 5 %).
- Fechas con hora: ``UTCDateTime`` (siempre UTC con zona, en SQLite y en PostgreSQL).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Enum, MetaData, Numeric, String, TypeDecorator, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# --- Tipos numéricos estándar (usar SIEMPRE estos en modelos) ---------------------------
Money = Numeric(18, 4, asdecimal=True)  # valores en pesos COP con 4 decimales internos
Qty = Numeric(18, 4, asdecimal=True)  # cantidades de obra
Coef = Numeric(18, 6, asdecimal=True)  # rendimientos / cantidades por unidad en APU
Pct = Numeric(9, 6, asdecimal=True)  # porcentajes como FRACCIÓN (0.05 = 5 %)


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """``DateTime(timezone=True)`` que SIEMPRE entrega datetimes UTC con zona.

    SQLite no guarda la zona (devuelve valores naive) y PostgreSQL los devuelve en la zona de la
    sesión (p. ej. -05:00): sin normalizar, la API serializaría el mismo instante de tres formas
    y el frontend interpretaría los naive como hora local. Al guardar: naive = UTC; al leer: UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, _dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Campos de auditoría básica. ``created_by``/``updated_by`` se llenan solos (ver abajo)."""

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(150))
    updated_by: Mapped[str | None] = mapped_column(String(150))


def _connect_args(url: str) -> dict[str, Any]:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def build_engine(url: str, echo: bool = False, **kwargs: Any) -> Engine:
    eng = create_engine(url, echo=echo, connect_args=_connect_args(url), **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


engine = build_engine(settings.DATABASE_URL, settings.SQL_ECHO)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

# Clave en ``Session.info`` donde la capa de seguridad deja el usuario de la petición.
SESSION_USER_KEY = "username"


@event.listens_for(Session, "before_flush")
def _llenar_campos_auditoria(session: Session, _ctx: Any, _instances: Any) -> None:
    """Llena created_by / updated_by con el usuario de la petición (o 'sistema')."""
    usuario = session.info.get(SESSION_USER_KEY) or "sistema"
    for obj in session.new:
        if isinstance(obj, TimestampMixin):
            if obj.created_by is None:
                obj.created_by = usuario
            obj.updated_by = usuario
    for obj in session.dirty:
        if isinstance(obj, TimestampMixin) and session.is_modified(obj, include_collections=False):
            obj.updated_by = usuario


def get_db() -> Iterator[Session]:
    """Dependencia FastAPI: una sesión por petición. Los services hacen commit explícito."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def str_enum(enum_cls: type[Any], length: int = 20) -> Enum:
    """Columna Enum portable (VARCHAR + CHECK), sin tipos ENUM nativos de PostgreSQL."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
        create_constraint=True,
    )
