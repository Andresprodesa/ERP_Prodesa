"""Esquemas Pydantic v2 de ADPRO / control (request/response del contrato).

Usar ``app.core.schemas.ORMModel`` como base de respuestas y ``Page[T]`` para listados.
Decimales como ``Decimal`` (se serializan como string). Porcentajes como fracción.
"""

from __future__ import annotations
