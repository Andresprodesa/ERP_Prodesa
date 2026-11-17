"""Escenario SINTÉTICO compartido por los tests de apu y presupuesto (datos ficticios).

Precios (ciudad BOG):
    Lista L1 desde 2026-01-01: CEM 1000/KG, ARENA 50000/M3, MO 20000/HR, EQ 8000/HR
    Lista L2 desde 2026-07-01: CEM 1200/KG (el resto se toma de L1)
    SUB-001 no tiene precio en ninguna lista. INA-001 está inactivo.

EDT:
    01 Preliminares > 01.01 > 01.01.001 > 01.01.001.0001 Muro (M2)      [APU muro]
                                        > 01.01.001.0002 Concreto (M3)  [APU concreto]
    02 Estructura   > 02.01 > 02.01.001 > 02.01.001.0001 Losa (M2)      [sin APU]
                                        > 02.01.001.0002 Pañete (M2)    [sin APU; los tests lo crean]

APU muro (por M2):      CEM 2 KG desp 5 %  +  MO 0.5 HR desp 0
    a 2026-03-01: 2·1.05·1000 + 0.5·20000 = 2100 + 10000 = 12100
    a 2026-08-01: 2·1.05·1200 + 10000      = 2520 + 10000 = 12520
APU concreto (por M3):  CEM 350 KG desp 3 %  +  ARENA 0.55 M3 desp 10 %  +  EQ 0.333333 HR desp 0
    a 2026-03-01: 360500 + 30250 + 2666.664 = 393416.6640
    a 2026-08-01: 432600 + 30250 + 2666.664 = 465516.6640
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.adpro.enums import NivelEdt, TipoInsumo, TipoProyecto
from app.modules.adpro.models import (
    Apu,
    ApuInsumo,
    Ciudad,
    EdtNodo,
    Etapa,
    Insumo,
    ListaPrecios,
    PrecioInsumo,
    Proyecto,
    Unidad,
)

D = Decimal
F_MAR = date(2026, 3, 1)
F_AGO = date(2026, 8, 1)


def _nodo(db: Session, nivel: NivelEdt, codigo: str, desc: str, parent: EdtNodo | None, unidad_id=None):  # type: ignore[no-untyped-def]
    n = EdtNodo(
        nivel=nivel,
        codigo=codigo,
        descripcion=desc,
        parent_id=parent.id if parent else None,
        unidad_id=unidad_id,
    )
    db.add(n)
    db.flush()
    return n


def crear_escenario(db: Session) -> dict[str, int]:
    u = {c: Unidad(codigo=c, nombre=c) for c in ("M2", "M3", "KG", "HR", "UN")}
    db.add_all(u.values())
    bog = Ciudad(codigo="BOG", nombre="Bogotá D.C.")
    mde = Ciudad(codigo="MDE", nombre="Medellín")
    db.add_all([bog, mde])
    db.flush()

    ins = {
        "cem": Insumo(
            codigo="MAT-001", descripcion="Cemento gris (demo)", unidad_id=u["KG"].id, tipo=TipoInsumo.MAT
        ),
        "arena": Insumo(
            codigo="MAT-002", descripcion="Arena lavada (demo)", unidad_id=u["M3"].id, tipo=TipoInsumo.MAT
        ),
        "mo": Insumo(
            codigo="MO-001",
            descripcion="Cuadrilla oficial+ayudante (demo)",
            unidad_id=u["HR"].id,
            tipo=TipoInsumo.MO,
        ),
        "eq": Insumo(
            codigo="EQ-001", descripcion="Mezcladora (demo)", unidad_id=u["HR"].id, tipo=TipoInsumo.EQ
        ),
        "sub": Insumo(
            codigo="SUB-001",
            descripcion="Subcontrato demo sin precio",
            unidad_id=u["UN"].id,
            tipo=TipoInsumo.SUB,
        ),
        "ina": Insumo(
            codigo="INA-001",
            descripcion="Insumo inactivo (demo)",
            unidad_id=u["UN"].id,
            tipo=TipoInsumo.MAT,
            activo=False,
        ),
    }
    db.add_all(ins.values())
    db.flush()

    c1 = _nodo(db, NivelEdt.CAPITULO, "01", "Preliminares", None)
    d1 = _nodo(db, NivelEdt.DETALLE, "01.01", "Muros", c1)
    g1 = _nodo(db, NivelEdt.GRUPO, "01.01.001", "Muros en bloque", d1)
    muro = _nodo(db, NivelEdt.ITEM, "01.01.001.0001", "Muro en bloque (demo)", g1, u["M2"].id)
    concreto = _nodo(db, NivelEdt.ITEM, "01.01.001.0002", "Concreto 3000 psi (demo)", g1, u["M3"].id)
    c2 = _nodo(db, NivelEdt.CAPITULO, "02", "Estructura", None)
    d2 = _nodo(db, NivelEdt.DETALLE, "02.01", "Losas", c2)
    g2 = _nodo(db, NivelEdt.GRUPO, "02.01.001", "Losas macizas", d2)
    losa = _nodo(db, NivelEdt.ITEM, "02.01.001.0001", "Losa maciza (demo)", g2, u["M2"].id)
    panete = _nodo(db, NivelEdt.ITEM, "02.01.001.0002", "Pañete liso (demo)", g2, u["M2"].id)

    l1 = ListaPrecios(
        codigo="BOG-2026-01", nombre="BOG enero", ciudad_id=bog.id, fecha_desde=date(2026, 1, 1)
    )
    l2 = ListaPrecios(
        codigo="BOG-2026-07", nombre="BOG julio", ciudad_id=bog.id, fecha_desde=date(2026, 7, 1)
    )
    db.add_all([l1, l2])
    db.flush()
    db.add_all(
        [
            PrecioInsumo(lista_id=l1.id, insumo_id=ins["cem"].id, precio=D("1000")),
            PrecioInsumo(lista_id=l1.id, insumo_id=ins["arena"].id, precio=D("50000")),
            PrecioInsumo(lista_id=l1.id, insumo_id=ins["mo"].id, precio=D("20000")),
            PrecioInsumo(lista_id=l1.id, insumo_id=ins["eq"].id, precio=D("8000")),
            PrecioInsumo(lista_id=l2.id, insumo_id=ins["cem"].id, precio=D("1200")),
        ]
    )

    apu_muro = Apu(item_id=muro.id, descripcion="APU muro demo")
    apu_muro.insumos = [
        ApuInsumo(insumo_id=ins["cem"].id, cantidad=D("2"), desperdicio_pct=D("0.05"), orden=1),
        ApuInsumo(insumo_id=ins["mo"].id, cantidad=D("0.5"), desperdicio_pct=D("0"), orden=2),
    ]
    apu_conc = Apu(item_id=concreto.id, descripcion="APU concreto demo")
    apu_conc.insumos = [
        ApuInsumo(insumo_id=ins["cem"].id, cantidad=D("350"), desperdicio_pct=D("0.03"), orden=1),
        ApuInsumo(insumo_id=ins["arena"].id, cantidad=D("0.55"), desperdicio_pct=D("0.10"), orden=2),
        ApuInsumo(insumo_id=ins["eq"].id, cantidad=D("0.333333"), desperdicio_pct=D("0"), orden=3),
    ]
    db.add_all([apu_muro, apu_conc])

    proyecto = Proyecto(
        codigo="PRY-DEMO-01", nombre="Proyecto Demo Ficticio", ciudad_id=bog.id, tipo=TipoProyecto.VIS
    )
    db.add(proyecto)
    db.flush()
    etapa = Etapa(proyecto_id=proyecto.id, codigo="E1", nombre="Etapa 1 demo")
    otro = Proyecto(
        codigo="PRY-DEMO-02", nombre="Otro proyecto ficticio", ciudad_id=mde.id, tipo=TipoProyecto.NO_VIS
    )
    db.add_all([etapa, otro])
    db.flush()
    etapa_otro = Etapa(proyecto_id=otro.id, codigo="E1", nombre="Etapa otro")
    db.add(etapa_otro)
    db.commit()
    return {
        "bog": bog.id,
        "mde": mde.id,
        "cem": ins["cem"].id,
        "arena": ins["arena"].id,
        "mo": ins["mo"].id,
        "eq": ins["eq"].id,
        "sub": ins["sub"].id,
        "ina": ins["ina"].id,
        "cap01": c1.id,
        "cap02": c2.id,
        "grupo01": g1.id,
        "muro": muro.id,
        "concreto": concreto.id,
        "losa": losa.id,
        "panete": panete.id,
        "apu_muro": apu_muro.id,
        "apu_concreto": apu_conc.id,
        "l1": l1.id,
        "l2": l2.id,
        "proyecto": proyecto.id,
        "etapa": etapa.id,
        "proyecto2": otro.id,
        "etapa_otro": etapa_otro.id,
    }
