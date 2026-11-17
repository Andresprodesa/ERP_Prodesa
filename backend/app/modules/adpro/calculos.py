"""Cálculos puros del dominio ADPRO (sin BD, sin FastAPI). Fuente ÚNICA de las fórmulas.

PROPIEDAD: agente ARQUITECTO. Los submódulos (apu, presupuesto, control) DEBEN usar estas
funciones en lugar de reimplementar fórmulas, para que todos los números cuadren.

Política de redondeo (ROUND_HALF_UP en todo):
- Componentes y valores unitarios: 4 decimales (``q4``), tipo Money Numeric(18,4).
- Valor total de línea: ``redondear_pesos(cantidad * valor_unitario)`` (pesos enteros).
- Totales por capítulo / costo directo: suma de valores totales de línea (ya en pesos).
- AIU e IVA: cada componente se redondea a pesos sobre el costo directo / utilidad.
- Porcentajes como FRACCIÓN (0.05 = 5 %); variaciones con 6 decimales.
- Explosión de insumos: la cantidad se redondea (q4) SOLO para mostrar; el valor se calcula
  con la cantidad exacta, para que la explosión cuadre con el costo directo (dif. de pesos).
- Rango: todo valor monetario o cantidad cabe en Numeric(18,4) (|x| < 10^14); si un producto
  lo excede se lanza ``BusinessRuleError`` (422) ANTES de llegar a la BD (motor-agnóstico).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import BusinessRuleError

ZERO = Decimal("0")
ONE = Decimal("1")
_PESO = Decimal("1")
_Q4 = Decimal("0.0001")
_Q6 = Decimal("0.000001")
_PERIODO_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# Numeric(18,4): 14 dígitos enteros. Límite EXCLUSIVO para Money/Qty.
MAX_NUMERIC_18_4 = Decimal("1e14")


def to_decimal(value: Decimal | int | str | float | None) -> Decimal:
    """Convierte a Decimal de forma segura (float vía str para evitar artefactos binarios)."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def redondear_pesos(value: Decimal | int | str | float) -> Decimal:
    """Redondeo final a pesos COP enteros, ROUND_HALF_UP."""
    return to_decimal(value).quantize(_PESO, rounding=ROUND_HALF_UP)


def q4(value: Decimal | int | str | float) -> Decimal:
    return to_decimal(value).quantize(_Q4, rounding=ROUND_HALF_UP)


def q6(value: Decimal | int | str | float) -> Decimal:
    return to_decimal(value).quantize(_Q6, rounding=ROUND_HALF_UP)


def asegurar_rango(valor: Decimal, etiqueta: str = "valor") -> Decimal:
    """Verifica que ``valor`` quepa en Numeric(18,4); si no, ``BusinessRuleError`` (422)."""
    if abs(to_decimal(valor)) >= MAX_NUMERIC_18_4:
        raise BusinessRuleError(
            f"El {etiqueta} excede el máximo permitido (menos de 10^14)",
            details={"campo": etiqueta, "valor": str(valor)},
        )
    return valor


# --- APU ---------------------------------------------------------------------------------
def cantidad_con_desperdicio(cantidad: Decimal, desperdicio_pct: Decimal) -> Decimal:
    return to_decimal(cantidad) * (ONE + to_decimal(desperdicio_pct))


def valor_componente(cantidad: Decimal, desperdicio_pct: Decimal, precio: Decimal) -> Decimal:
    """Aporte de un insumo al valor unitario del ítem: cantidad·(1+desperdicio)·precio (q4)."""
    return q4(cantidad_con_desperdicio(cantidad, desperdicio_pct) * to_decimal(precio))


def valor_unitario_apu(componentes: Iterable[tuple[Decimal, Decimal, Decimal]]) -> Decimal:
    """Σ valor_componente(cantidad, desperdicio, precio) para tuplas (cantidad, desperdicio, precio)."""
    return q4(sum((valor_componente(c, d, p) for c, d, p in componentes), ZERO))


# --- Presupuesto -------------------------------------------------------------------------
def valor_total_linea(cantidad: Decimal, valor_unitario: Decimal) -> Decimal:
    """redondear_pesos(cantidad · valor_unitario); 422 si el resultado no cabe en Numeric(18,4)."""
    asegurar_rango(to_decimal(valor_unitario), "valor unitario")
    return asegurar_rango(redondear_pesos(to_decimal(cantidad) * to_decimal(valor_unitario)), "valor total")


def cantidad_exacta_insumo(
    cantidad_linea: Decimal, cantidad_unitaria: Decimal, desperdicio_pct: Decimal
) -> Decimal:
    """Cantidad del insumo en una línea SIN redondear: cant_línea · cant_unitaria · (1+desperdicio).
    Úsela para valorizar (``valor_total_insumo``); redondee con ``q4`` solo para mostrar."""
    return to_decimal(cantidad_linea) * cantidad_con_desperdicio(cantidad_unitaria, desperdicio_pct)


def cantidad_total_insumo(
    cantidad_linea: Decimal, cantidad_unitaria: Decimal, desperdicio_pct: Decimal
) -> Decimal:
    """Cantidad del insumo en una línea para MOSTRAR (q4)."""
    return q4(cantidad_exacta_insumo(cantidad_linea, cantidad_unitaria, desperdicio_pct))


def valor_total_insumo(cantidad: Decimal, precio_unitario: Decimal) -> Decimal:
    """Valor del insumo en pesos. ``cantidad`` debe ser la EXACTA (``cantidad_exacta_insumo``):
    valorizar una cantidad ya redondeada a 4 decimales descuadra miles de pesos con insumos caros."""
    return redondear_pesos(to_decimal(cantidad) * to_decimal(precio_unitario))


@dataclass(frozen=True)
class ResultadoAIU:
    costo_directo: Decimal
    administracion: Decimal
    imprevistos: Decimal
    utilidad: Decimal
    iva_utilidad: Decimal
    total_aiu: Decimal  # A + I + U (sin IVA)
    total: Decimal  # costo directo + AIU + IVA sobre utilidad


def calcular_aiu(
    costo_directo: Decimal,
    administracion_pct: Decimal,
    imprevistos_pct: Decimal,
    utilidad_pct: Decimal,
    iva_utilidad_pct: Decimal,
) -> ResultadoAIU:
    cd = redondear_pesos(costo_directo)
    a = redondear_pesos(cd * to_decimal(administracion_pct))
    i = redondear_pesos(cd * to_decimal(imprevistos_pct))
    u = redondear_pesos(cd * to_decimal(utilidad_pct))
    iva = redondear_pesos(u * to_decimal(iva_utilidad_pct))
    return ResultadoAIU(
        costo_directo=cd,
        administracion=a,
        imprevistos=i,
        utilidad=u,
        iva_utilidad=iva,
        total_aiu=a + i + u,
        total=cd + a + i + u + iva,
    )


def participacion_pct(parte: Decimal | int | str, total: Decimal | int | str) -> Decimal | None:
    """parte / total como FRACCIÓN con 6 decimales (participación o % de avance).

    None si el total es 0 (no hay base contra la cual medir).
    """
    t = to_decimal(total)
    if t == ZERO:
        return None
    return q6(to_decimal(parte) / t)


# --- Control -----------------------------------------------------------------------------
def variacion_pct(base: Decimal | None, comparado: Decimal | None) -> Decimal | None:
    """(comparado - base) / base como fracción (6 decimales). None si la base es 0/None."""
    b = to_decimal(base)
    if b == ZERO:
        return None
    return q6((to_decimal(comparado) - b) / b)


def es_periodo_valido(periodo: str) -> bool:
    """Periodo mensual 'YYYY-MM'."""
    return bool(_PERIODO_RE.match(periodo or ""))
