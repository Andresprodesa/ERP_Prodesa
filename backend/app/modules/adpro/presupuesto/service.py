"""Lógica de negocio de ADPRO / presupuesto.

Funciones puras respecto a HTTP: reciben ``db: Session`` y datos validados, devuelven modelos
o dataclasses, y lanzan ``app.core.errors`` (NotFoundError, ConflictError, BusinessRuleError).
Hacen ``db.commit()`` al final de cada operación de escritura y registran auditoría con
``app.core.audit.registrar_auditoria`` en operaciones relevantes.
Fórmulas: usar SIEMPRE ``app.modules.adpro.calculos`` y ``app.modules.adpro.valorizacion``.
"""

from __future__ import annotations
