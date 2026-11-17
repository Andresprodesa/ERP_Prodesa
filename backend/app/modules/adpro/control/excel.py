"""Utilidades openpyxl de ADPRO / control (sin BD ni FastAPI).

- Escritura de tablas con encabezado con formato, anchos de columna, filas congeladas y
  formatos numéricos (miles para pesos, decimales para cantidades/unitarios, % para fracciones).
- Lectura de la plantilla de importación de presupuesto.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from io import BytesIO
from typing import Any, Literal

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

_MILES_RE = re.compile(r"^-?\d{1,3}(\.\d{3})+$")

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Colores corporativos aproximados (azul institucional / gris claro). Ajustables en un solo lugar.
COLOR_ENCABEZADO = "003B71"
COLOR_TOTAL = "E7ECF3"

HOJA_PLANTILLA = "Presupuesto"
ENCABEZADOS_PLANTILLA: tuple[str, ...] = (
    "codigo_item",
    "descripcion",
    "unidad",
    "cantidad",
    "valor_unitario",
    "observacion",
)

Formato = Literal["texto", "pesos", "decimal", "cantidad", "pct", "entero"]
_NUMBER_FORMATS: dict[str, str] = {
    "pesos": "#,##0",
    "decimal": "#,##0.00",
    "cantidad": "#,##0.0000",
    "pct": "0.00%",
    "entero": "0",
}

_BORDE = Border(bottom=Side(style="thin", color="B0B7C3"))


@dataclass(frozen=True)
class Columna:
    titulo: str
    formato: Formato = "texto"
    ancho: int = 14


def nuevo_libro() -> Workbook:
    wb = Workbook()
    # Se elimina la hoja por defecto; cada exportación crea las suyas con nombre.
    wb.remove(wb.active)  # type: ignore[arg-type]
    return wb


def a_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _valor_celda(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value  # (str, Enum): str(v) daría "Clase.MIEMBRO"
    return v


def escribir_tabla(
    ws: Worksheet,
    columnas: Sequence[Columna],
    filas: Iterable[Sequence[Any]],
    *,
    fila_inicio: int = 1,
    total: Sequence[Any] | None = None,
) -> int:
    """Escribe encabezado + filas (+ fila de total opcional). Devuelve la última fila escrita."""
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=COLOR_ENCABEZADO)
    for j, col in enumerate(columnas, start=1):
        c = ws.cell(row=fila_inicio, column=j, value=col.titulo)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(j)].width = col.ancho
    r = fila_inicio
    for fila in filas:
        r += 1
        _escribir_fila(ws, r, columnas, fila)
    if total is not None:
        r += 1
        _escribir_fila(ws, r, columnas, total)
        for j in range(1, len(columnas) + 1):
            c = ws.cell(row=r, column=j)
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor=COLOR_TOTAL)
    if fila_inicio == 1:
        ws.freeze_panes = "A2"
    return r


def _escribir_fila(ws: Worksheet, r: int, columnas: Sequence[Columna], fila: Sequence[Any]) -> None:
    for j, (col, v) in enumerate(zip(columnas, fila, strict=False), start=1):
        c = ws.cell(row=r, column=j, value=_valor_celda(v))
        c.border = _BORDE
        fmt = _NUMBER_FORMATS.get(col.formato)
        if fmt and v is not None:
            c.number_format = fmt


def escribir_pares(ws: Worksheet, pares: Sequence[tuple[str, Any, Formato]], *, fila_inicio: int = 1) -> int:
    """Bloque etiqueta/valor (encabezado de resumen). Devuelve la última fila escrita."""
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width or 0, 28)
    ws.column_dimensions["B"].width = max(ws.column_dimensions["B"].width or 0, 22)
    r = fila_inicio - 1
    for etiqueta, valor, formato in pares:
        r += 1
        ws.cell(row=r, column=1, value=etiqueta).font = Font(bold=True)
        c = ws.cell(row=r, column=2, value=_valor_celda(valor))
        fmt = _NUMBER_FORMATS.get(formato)
        if fmt and valor is not None:
            c.number_format = fmt
    return r


# --- Lectura de la plantilla ----------------------------------------------------------------
class ArchivoInvalidoError(ValueError):
    """El archivo no es un .xlsx legible."""


@dataclass
class FilaPlantilla:
    fila: int
    codigo_item: str | None
    descripcion: str | None
    unidad: str | None
    cantidad: Any
    valor_unitario: Any
    observacion: str | None


@dataclass
class LecturaPlantilla:
    filas: list[FilaPlantilla]
    errores: list[tuple[int, str | None, str]]  # (fila, columna, mensaje)


def _texto(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def leer_plantilla(contenido: bytes) -> LecturaPlantilla:
    """Lee la hoja ``Presupuesto``. Encabezados por nombre (columnas extra se ignoran)."""
    try:
        wb = load_workbook(BytesIO(contenido), read_only=True, data_only=True)
    except Exception as exc:  # zipfile.BadZipFile, KeyError, InvalidFileException...
        raise ArchivoInvalidoError("El archivo no es un Excel .xlsx válido") from exc
    try:
        if HOJA_PLANTILLA not in wb.sheetnames:
            return LecturaPlantilla([], [(1, None, f"No existe la hoja '{HOJA_PLANTILLA}'")])
        ws = wb[HOJA_PLANTILLA]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            return LecturaPlantilla([], [(1, None, "La hoja está vacía")])
        idx = {str(h).strip().lower(): i for i, h in enumerate(header) if h is not None}
        faltan = [h for h in ENCABEZADOS_PLANTILLA if h not in idx]
        if faltan:
            return LecturaPlantilla([], [(1, h, f"Falta la columna de encabezado '{h}'") for h in faltan])

        def get(row: Sequence[Any], col: str) -> Any:
            i = idx[col]
            return row[i] if i < len(row) else None

        filas: list[FilaPlantilla] = []
        for n, row in enumerate(rows, start=2):
            if row is None or all(v is None or (isinstance(v, str) and not v.strip()) for v in row):
                continue
            filas.append(
                FilaPlantilla(
                    fila=n,
                    codigo_item=_texto(get(row, "codigo_item")),
                    descripcion=_texto(get(row, "descripcion")),
                    unidad=_texto(get(row, "unidad")),
                    cantidad=get(row, "cantidad"),
                    valor_unitario=get(row, "valor_unitario"),
                    observacion=_texto(get(row, "observacion")),
                )
            )
        return LecturaPlantilla(filas, [])
    finally:
        wb.close()


def parse_decimal(v: Any) -> Decimal | None:
    """Convierte un valor de celda a Decimal. ``None`` si vacío; ``ValueError`` si no es número.

    Acepta números de Excel y textos como ``"1250.5"``, ``"1.250,5"`` o ``"1250,5"``.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError("valor no numérico")
    if isinstance(v, int | Decimal):
        return Decimal(v)
    if isinstance(v, float):
        return Decimal(str(v))
    s = str(v).strip().replace(" ", "").replace("$", "")
    if not s:
        return None
    if "," in s or _MILES_RE.match(s):
        # Formato colombiano: punto de miles, coma decimal ("1.250,5", "1.000").
        s = s.replace(".", "").replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError("valor no numérico") from exc
    if not d.is_finite():
        raise ValueError("valor no numérico")
    return d
