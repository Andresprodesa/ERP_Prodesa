"""Guarda de rendimiento: las lecturas principales no hacen N+1 consultas (datos demo sintéticos)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session

from app.core.models import Rol
from app.modules.adpro.enums import EstadoVersion
from app.modules.adpro.models import PresupuestoVersion
from app.seed import run as seed_run

MAX_CONSULTAS = 20  # con ~40 líneas / ~70 insumos, un N+1 superaría holgadamente este tope


def test_lecturas_principales_sin_n_mas_1(
    db: Session, engine: Engine, client_as: Callable[[Rol | str], TestClient]
) -> None:
    seed_run(db)
    c = client_as(Rol.CONSULTA)
    v = db.scalars(
        select(PresupuestoVersion).where(PresupuestoVersion.estado == EstadoVersion.APROBADO)
    ).first()
    assert v is not None
    otra = db.scalars(
        select(PresupuestoVersion).where(
            PresupuestoVersion.presupuesto_id == v.presupuesto_id, PresupuestoVersion.id != v.id
        )
    ).first()
    assert otra is not None
    rutas = [
        "/api/adpro/presupuestos",
        f"/api/adpro/presupuestos/versiones/{v.id}/lineas",
        f"/api/adpro/presupuestos/versiones/{v.id}/resumen",
        f"/api/adpro/presupuestos/versiones/{v.id}/explosion",
        f"/api/adpro/control/comparativo?version_base_id={v.id}&version_comparada_id={otra.id}&nivel=insumo",
        f"/api/adpro/control/tablero/items?presupuesto_id={v.presupuesto_id}",
        "/api/adpro/apu/apus?limit=500",
        "/api/adpro/maestros/insumos?limit=500",
        f"/api/adpro/control/excel/presupuesto/{v.id}",
    ]
    contador = {"n": 0}

    def _contar(*_a, **_k) -> None:  # type: ignore[no-untyped-def]
        contador["n"] += 1

    event.listen(engine, "before_cursor_execute", _contar)
    try:
        excesos = []
        for ruta in rutas:
            contador["n"] = 0
            assert c.get(ruta).status_code == 200, ruta
            if contador["n"] > MAX_CONSULTAS:
                excesos.append((ruta, contador["n"]))
    finally:
        event.remove(engine, "before_cursor_execute", _contar)
    assert excesos == []
