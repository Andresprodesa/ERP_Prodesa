"""indices de busqueda por texto (pg_trgm) en insumo y edt_nodo

Los filtros ``q`` de maestros usan ``lower(columna) LIKE '%texto%'``. Un índice B-tree no sirve
para un LIKE con comodín inicial; en PostgreSQL sí lo aprovecha un índice GIN con ``pg_trgm``
sobre la MISMA expresión ``lower(columna)``.

Solo aplica en PostgreSQL. En SQLite (prototipo local) la migración no hace nada.
Si el usuario de la BD no puede crear la extensión (p. ej. un servicio administrado sin
``pg_trgm`` habilitado), la migración no falla: deja un NOTICE y no crea los índices.

Estos índices NO se declaran en ``models.py`` (son específicos de PostgreSQL). ``alembic/env.py``
excluye de la comparación de autogenerate los índices con prefijo ``ix_trgm_``.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17 18:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (nombre del índice, tabla, columna)
_INDICES: tuple[tuple[str, str, str], ...] = (
    ("ix_trgm_adpro_insumo_codigo", "adpro_insumo", "codigo"),
    ("ix_trgm_adpro_insumo_descripcion", "adpro_insumo", "descripcion"),
    ("ix_trgm_adpro_edt_nodo_codigo", "adpro_edt_nodo", "codigo"),
    ("ix_trgm_adpro_edt_nodo_descripcion", "adpro_edt_nodo", "descripcion"),
)


def _es_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def upgrade() -> None:
    """Upgrade schema."""
    if not _es_postgresql():
        return
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
        EXCEPTION WHEN insufficient_privilege OR feature_not_supported OR undefined_file THEN
            RAISE NOTICE 'pg_trgm no disponible: se omiten los indices de busqueda por texto';
        END
        $$;
        """
    )
    creates = "\n".join(
        f"CREATE INDEX IF NOT EXISTS {nombre} ON {tabla} USING gin (lower({columna}) gin_trgm_ops);"
        for nombre, tabla, columna in _INDICES
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
                {creates}
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    if not _es_postgresql():
        return
    for nombre, _tabla, _columna in _INDICES:
        op.execute(f"DROP INDEX IF EXISTS {nombre}")
    # La extensión pg_trgm se deja instalada: puede usarla otro objeto de la BD.
