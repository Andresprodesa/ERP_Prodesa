"""Router agregador del módulo ADPRO (prefijo /api/adpro). Propiedad: ARQUITECTO."""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.adpro.apu.router import router as apu_router
from app.modules.adpro.control.router import router as control_router
from app.modules.adpro.maestros.router import router as maestros_router
from app.modules.adpro.presupuesto.router import router as presupuesto_router

router = APIRouter(prefix="/api/adpro")
router.include_router(maestros_router)
router.include_router(apu_router)
router.include_router(presupuesto_router)
router.include_router(control_router)
