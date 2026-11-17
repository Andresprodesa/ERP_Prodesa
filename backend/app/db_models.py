"""Registro de TODOS los modelos para que ``Base.metadata`` esté completo.

Lo importan Alembic (env.py), los tests (create_all) y el seed. Al agregar un módulo nuevo
(compras, contratos, ...), importe aquí su ``models.py``.
"""

from __future__ import annotations

from app.core import models as core_models  # noqa: F401
from app.core.db import Base
from app.modules.adpro import models as adpro_models  # noqa: F401

metadata = Base.metadata
