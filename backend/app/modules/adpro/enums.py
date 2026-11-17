"""Enumeraciones del dominio ADPRO (compartidas por modelos, schemas y services).

Se persisten como VARCHAR + CHECK (ver ``app.core.db.str_enum``); el valor JSON es el
mismo string del miembro (p. ej. ``"MAT"``).
"""

from __future__ import annotations

import enum


class TipoInsumo(str, enum.Enum):
    MAT = "MAT"  # material
    MO = "MO"  # mano de obra
    EQ = "EQ"  # equipo
    TR = "TR"  # transporte
    SUB = "SUB"  # subcontrato


class TipoProyecto(str, enum.Enum):
    VIS = "VIS"
    VIP = "VIP"
    NO_VIS = "NO_VIS"


class EstadoProyecto(str, enum.Enum):
    PLANEACION = "PLANEACION"
    EN_EJECUCION = "EN_EJECUCION"
    TERMINADO = "TERMINADO"
    SUSPENDIDO = "SUSPENDIDO"


class NivelEdt(str, enum.Enum):
    """Niveles de la EDT presupuestal estilo ProdesaClass (orden jerárquico estricto)."""

    CAPITULO = "CAPITULO"
    DETALLE = "DETALLE"
    GRUPO = "GRUPO"
    ITEM = "ITEM"

    @property
    def profundidad(self) -> int:
        return _PROFUNDIDAD[self]

    @property
    def padre_requerido(self) -> NivelEdt | None:
        """Nivel que debe tener el padre (None para CAPITULO, que es raíz)."""
        idx = _PROFUNDIDAD[self]
        return None if idx == 1 else _ORDEN[idx - 2]


_ORDEN = [NivelEdt.CAPITULO, NivelEdt.DETALLE, NivelEdt.GRUPO, NivelEdt.ITEM]
_PROFUNDIDAD = {n: i + 1 for i, n in enumerate(_ORDEN)}


class TipoVersion(str, enum.Enum):
    BASE = "BASE"  # presupuesto base / licitación interna
    FIC = "FIC"  # factibilidad / control inicial
    FIV = "FIV"  # validación
    CONTROL = "CONTROL"  # presupuesto de control de obra (contra el que se compromete/ejecuta)
    OTRO = "OTRO"


class EstadoVersion(str, enum.Enum):
    BORRADOR = "BORRADOR"  # editable
    APROBADO = "APROBADO"  # inmutable; precios congelados (snapshot)
    CERRADO = "CERRADO"  # histórico; inmutable

    @property
    def editable(self) -> bool:
        return self is EstadoVersion.BORRADOR


class OrigenValor(str, enum.Enum):
    """De dónde salió el valor unitario de una línea de presupuesto."""

    APU = "APU"
    MANUAL = "MANUAL"
    IMPORTADO = "IMPORTADO"


class TipoCompromiso(str, enum.Enum):
    ORDEN_COMPRA = "ORDEN_COMPRA"
    CONTRATO = "CONTRATO"
    ORDEN_SERVICIO = "ORDEN_SERVICIO"


class EstadoCompromiso(str, enum.Enum):
    VIGENTE = "VIGENTE"
    LIQUIDADO = "LIQUIDADO"
    ANULADO = "ANULADO"  # no suma en el tablero
