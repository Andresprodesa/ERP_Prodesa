"""Endpoints REST de ADPRO / apu (prefijo final: /api/adpro/apu).

Contrato: docs/API_CONTRATO.md (sección apu). Reglas:
- Routers delgados: validan entrada (schemas), aplican roles (``require_role``) y delegan en
  ``service.py``. Nada de lógica de negocio aquí.
- Lectura: cualquier usuario autenticado (``CurrentUser``). Escritura: ver roles del contrato.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/apu", tags=["ADPRO - APU"])
