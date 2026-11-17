"""Fixtures del submódulo control: escenario sintético construido directamente con modelos.

Escenario (precios BOG desde 2026-01-01; datos ficticios):

    Insumos: MAT-001 cemento 1.000/KG, MO-001 cuadrilla 20.000/DIA, MAT-002 bloque 5.000/UN
    EDT: 01 Preliminares > 01.01 > 01.01.001 > ITEM A 01.01.001.0001 (M2, APU)  vu 12.100
                                               ITEM B 01.01.001.0002 (M3, APU)  vu  5.000
         02 Estructura   > 02.01 > 02.01.001 > ITEM C 02.01.001.0001 (M3, sin APU)
                                               ITEM D 02.01.001.0002 (M3, sin APU)
    APU A: MAT-001 2 (desp 5 %) + MO-001 0,5   -> 2.100 + 10.000 = 12.100
    APU B: MAT-002 1                           -> 5.000

    v_fic (FIC, APROBADO):     A 100 (1.210.000)  B 10 (50.000)  C 2 x 300.000 manual (600.000) = 1.860.000
    v_control (CONTROL, APR.): igual a v_fic
    v_fiv (FIV, BORRADOR):     A 100 (igual)       B 12 (60.000)  D 5 x 1.000 manual (5.000)    = 1.275.000
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.adpro.calculos import valor_total_linea
from app.modules.adpro.enums import (
    EstadoVersion,
    NivelEdt,
    OrigenValor,
    TipoInsumo,
    TipoProyecto,
    TipoVersion,
)
from app.modules.adpro.models import (
    Apu,
    ApuInsumo,
    Ciudad,
    EdtNodo,
    Insumo,
    ListaPrecios,
    PrecioInsumo,
    Presupuesto,
    PresupuestoLinea,
    PresupuestoLineaInsumo,
    PresupuestoVersion,
    Proyecto,
    Unidad,
)
from app.modules.adpro.valorizacion import valorizar_apu

D = Decimal
FECHA_PRECIOS = date(2026, 3, 1)


@dataclass
class Escenario:
    ciudad: Ciudad
    proyecto: Proyecto
    presupuesto: Presupuesto
    cap1: EdtNodo
    cap2: EdtNodo
    item_a: EdtNodo
    item_b: EdtNodo
    item_c: EdtNodo
    item_d: EdtNodo
    cemento: Insumo
    cuadrilla: Insumo
    bloque: Insumo
    v_fic: PresupuestoVersion
    v_control: PresupuestoVersion
    v_fiv: PresupuestoVersion


def agregar_linea(
    db: Session,
    version: PresupuestoVersion,
    item: EdtNodo,
    cantidad: str,
    valor_unitario: str | None = None,
) -> PresupuestoLinea:
    """Crea una línea como lo haría presupuesto: APU (con snapshot) o MANUAL."""
    cant = D(cantidad)
    linea = PresupuestoLinea(version_id=version.id, item_id=item.id, cantidad=cant, orden=0)
    if valor_unitario is None:
        apu = db.scalar(select(Apu).where(Apu.item_id == item.id))
        assert apu is not None
        val = valorizar_apu(db, apu, version.ciudad_precios_id, version.fecha_precios)
        linea.valor_unitario = val.valor_unitario
        linea.origen_unitario = OrigenValor.APU
        for c in val.componentes:
            linea.insumos.append(
                PresupuestoLineaInsumo(
                    insumo_id=c.insumo_id,
                    cantidad_unitaria=c.cantidad,
                    desperdicio_pct=c.desperdicio_pct,
                    precio_unitario=c.precio_unitario,
                    valor_unitario=c.valor_unitario,
                    precio_faltante=c.precio_faltante,
                )
            )
    else:
        linea.valor_unitario = D(valor_unitario)
        linea.origen_unitario = OrigenValor.MANUAL
    linea.valor_total = valor_total_linea(cant, linea.valor_unitario)
    db.add(linea)
    db.flush()
    return linea


def nueva_version(
    db: Session,
    presupuesto: Presupuesto,
    numero: int,
    tipo: TipoVersion,
    estado: EstadoVersion = EstadoVersion.BORRADOR,
    nombre: str | None = None,
) -> PresupuestoVersion:
    v = PresupuestoVersion(
        presupuesto_id=presupuesto.id,
        numero=numero,
        tipo=tipo,
        estado=estado,
        nombre=nombre or f"{tipo.value} demo {numero}",
        fecha_precios=FECHA_PRECIOS,
        ciudad_precios_id=presupuesto.proyecto.ciudad_id,
        administracion_pct=D("0.08"),
        imprevistos_pct=D("0.02"),
        utilidad_pct=D("0.05"),
        iva_utilidad_pct=D("0.19"),
    )
    db.add(v)
    db.flush()
    return v


@pytest.fixture()
def escenario(seed_basico: Session) -> Escenario:
    db = seed_basico
    unidades = {u.codigo: u for u in db.scalars(select(Unidad))}
    bog = db.scalar(select(Ciudad).where(Ciudad.codigo == "BOG"))
    assert bog is not None

    cemento = Insumo(
        codigo="MAT-001", descripcion="Cemento gris demo", unidad_id=unidades["KG"].id, tipo=TipoInsumo.MAT
    )
    cuadrilla = Insumo(
        codigo="MO-001", descripcion="Cuadrilla demo", unidad_id=unidades["DIA"].id, tipo=TipoInsumo.MO
    )
    bloque = Insumo(
        codigo="MAT-002", descripcion="Bloque demo", unidad_id=unidades["UN"].id, tipo=TipoInsumo.MAT
    )
    db.add_all([cemento, cuadrilla, bloque])
    lista = ListaPrecios(
        codigo="LP-BOG-2026", nombre="Lista demo BOG 2026", ciudad_id=bog.id, fecha_desde=date(2026, 1, 1)
    )
    db.add(lista)
    db.flush()
    db.add_all(
        [
            PrecioInsumo(lista_id=lista.id, insumo_id=cemento.id, precio=D("1000")),
            PrecioInsumo(lista_id=lista.id, insumo_id=cuadrilla.id, precio=D("20000")),
            PrecioInsumo(lista_id=lista.id, insumo_id=bloque.id, precio=D("5000")),
        ]
    )

    def nodo(
        nivel: NivelEdt, codigo: str, desc: str, parent: EdtNodo | None = None, unidad: str | None = None
    ) -> EdtNodo:
        n = EdtNodo(
            nivel=nivel,
            codigo=codigo,
            descripcion=desc,
            parent_id=parent.id if parent else None,
            unidad_id=unidades[unidad].id if unidad else None,
        )
        db.add(n)
        db.flush()
        return n

    cap1 = nodo(NivelEdt.CAPITULO, "01", "Preliminares")
    g1 = nodo(
        NivelEdt.GRUPO, "01.01.001", "Grupo demo 1", nodo(NivelEdt.DETALLE, "01.01", "Detalle demo 1", cap1)
    )
    item_a = nodo(NivelEdt.ITEM, "01.01.001.0001", "Item A demo", g1, "M2")
    item_b = nodo(NivelEdt.ITEM, "01.01.001.0002", "Item B demo", g1, "M3")
    cap2 = nodo(NivelEdt.CAPITULO, "02", "Estructura")
    g2 = nodo(
        NivelEdt.GRUPO, "02.01.001", "Grupo demo 2", nodo(NivelEdt.DETALLE, "02.01", "Detalle demo 2", cap2)
    )
    item_c = nodo(NivelEdt.ITEM, "02.01.001.0001", "Item C demo", g2, "M3")
    item_d = nodo(NivelEdt.ITEM, "02.01.001.0002", "Item D demo", g2, "M3")

    apu_a = Apu(item_id=item_a.id, descripcion="APU A demo")
    apu_a.insumos = [
        ApuInsumo(insumo_id=cemento.id, cantidad=D("2"), desperdicio_pct=D("0.05"), orden=1),
        ApuInsumo(insumo_id=cuadrilla.id, cantidad=D("0.5"), desperdicio_pct=D("0"), orden=2),
    ]
    apu_b = Apu(item_id=item_b.id, descripcion="APU B demo")
    apu_b.insumos = [ApuInsumo(insumo_id=bloque.id, cantidad=D("1"), desperdicio_pct=D("0"), orden=1)]
    db.add_all([apu_a, apu_b])

    proyecto = Proyecto(
        codigo="PRY-DEMO-01", nombre="Proyecto Demo Uno", ciudad_id=bog.id, tipo=TipoProyecto.VIS
    )
    db.add(proyecto)
    db.flush()
    presupuesto = Presupuesto(proyecto_id=proyecto.id, codigo="PPTO-01", nombre="Presupuesto demo")
    db.add(presupuesto)
    db.flush()

    v_fic = nueva_version(db, presupuesto, 1, TipoVersion.FIC)
    v_control = nueva_version(db, presupuesto, 2, TipoVersion.CONTROL)
    for v in (v_fic, v_control):
        agregar_linea(db, v, item_a, "100")
        agregar_linea(db, v, item_b, "10")
        agregar_linea(db, v, item_c, "2", "300000")
        v.estado = EstadoVersion.APROBADO
    v_fiv = nueva_version(db, presupuesto, 3, TipoVersion.FIV)
    agregar_linea(db, v_fiv, item_a, "100")
    agregar_linea(db, v_fiv, item_b, "12")
    agregar_linea(db, v_fiv, item_d, "5", "1000")
    db.commit()
    return Escenario(
        bog,
        proyecto,
        presupuesto,
        cap1,
        cap2,
        item_a,
        item_b,
        item_c,
        item_d,
        cemento,
        cuadrilla,
        bloque,
        v_fic,
        v_control,
        v_fiv,
    )
