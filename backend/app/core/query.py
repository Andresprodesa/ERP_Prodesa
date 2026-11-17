"""Utilidades de consulta compartidas por todos los módulos (agnósticas del motor).

``contiene(col, q)``: búsqueda de texto "contiene", sin distinguir mayúsculas, con los
comodines ``%`` y ``_`` del usuario ESCAPADOS (``q='_'`` busca un guion bajo literal, no
"cualquier carácter"). Usa ``lower(col) LIKE lower(patrón)`` para aprovechar en PostgreSQL los
índices GIN ``pg_trgm`` sobre ``lower(codigo)`` / ``lower(descripcion)`` (migración 0002);
``ILIKE`` no los usa.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, func

_ESCAPE = "\\"


def patron_contiene(q: str) -> str:
    """Patrón LIKE ``%texto%`` en minúsculas con ``\\``, ``%`` y ``_`` escapados."""
    texto = q.strip().lower()
    texto = texto.replace(_ESCAPE, _ESCAPE * 2).replace("%", _ESCAPE + "%").replace("_", _ESCAPE + "_")
    return f"%{texto}%"


def contiene(col: Any, q: str) -> ColumnElement[bool]:
    """``lower(col) LIKE '%q%'`` con escape de comodines."""
    return func.lower(col).like(patron_contiene(q), escape=_ESCAPE)
