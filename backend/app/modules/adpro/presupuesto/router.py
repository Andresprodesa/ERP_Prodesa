"""Endpoints REST de ADPRO / presupuesto (prefijo final: /api/adpro/presupuestos).

Contrato: docs/API_CONTRATO.md (sección presupuesto). Reglas:
- Routers delgados: validan entrada (schemas), aplican roles (``require_role``) y delegan en
  ``service.py``. Nada de lógica de negocio aquí.
- Lectura: cualquier usuario autenticado (``CurrentUser``). Escritura: ver roles del contrato.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/presupuestos", tags=["ADPRO - Presupuesto"])
