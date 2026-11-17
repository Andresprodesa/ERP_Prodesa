"""Regresiones de la revisión (dominio + arquitectura) en el submódulo control.

- Lectura de números en texto de la plantilla Excel: un formato ambiguo/US se RECHAZA (antes
  '1,250.50' se leía como 1.2505, mil veces menor, sin error).
- Exportaciones Excel: un texto de usuario que empieza por '=' (u otro prefijo de fórmula) se
  escribe como TEXTO, nunca como fórmula (CSV/Excel injection).
- Compromisos: un valor que no cabe en Numeric(18,4) responde 422 (antes 500 en PostgreSQL).

Datos 100 % sintéticos (escenario de ``tests/adpro/control/conftest.py``).
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook

from app.modules.adpro.control import excel as xl
from tests.adpro.control.conftest import Escenario

D = Decimal
BASE = "/api/adpro/control"


def _plantilla(filas: list[tuple[Any, ...]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = xl.HOJA_PLANTILLA
    ws.append(list(xl.ENCABEZADOS_PLANTILLA))
    for f in filas:
        ws.append(list(f))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- parse_decimal ------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("250.000", D("250000")),  # punto de miles (es-CO)
        ("1.250,5", D("1250.5")),
        ("1.250.000,75", D("1250000.75")),
        ("1250,5", D("1250.5")),  # coma decimal
        ("1,25", D("1.25")),
        ("1250.5", D("1250.5")),  # punto decimal sin miles
        ("1.5", D("1.5")),
        ("-3,5", D("-3.5")),
        ("$ 1.000", D("1000")),
    ],
)
def test_parse_decimal_formatos_aceptados(texto: str, esperado: Decimal) -> None:
    assert xl.parse_decimal(texto) == esperado


@pytest.mark.parametrize("texto", ["1,250.50", "1,250,000", "1.2.3", "1.250,5,3", "12.50.000", "1e3", "--1"])
def test_parse_decimal_rechaza_formatos_ambiguos(texto: str) -> None:
    with pytest.raises(ValueError, match="formato numérico no reconocido"):
        xl.parse_decimal(texto)


def test_importacion_formato_us_se_rechaza_con_error_de_fila(client_as, escenario: Escenario) -> None:  # type: ignore[no-untyped-def]
    contenido = _plantilla([("02.01.001.0001", None, None, "1,250.50", 1000, None)])
    r = client_as("presupuesto").post(
        f"{BASE}/excel/presupuesto/{escenario.v_fiv.id}/importar",
        params={"modo": "agregar"},
        files={"file": ("p.xlsx", contenido, xl.XLSX_MEDIA_TYPE)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aplicado"] is False
    errores = [e for e in body["errores"] if e["columna"] == "cantidad"]
    assert len(errores) == 1 and errores[0]["fila"] == 2 and "1.250,5" in errores[0]["mensaje"]


# --- Excel injection -----------------------------------------------------------------------
@pytest.mark.parametrize("prefijo", ["=", "+", "-", "@"])
def test_excel_no_exporta_texto_de_usuario_como_formula(
    client_as,
    escenario: Escenario,
    prefijo: str,  # type: ignore[no-untyped-def]
) -> None:
    c = client_as("presupuesto")
    descripcion = f"{prefijo}1+1 REV"
    r = c.put(f"/api/adpro/maestros/insumos/{escenario.cemento.id}", json={"descripcion": descripcion})
    assert r.status_code == 200, r.text
    for ruta in (
        f"{BASE}/excel/explosion/{escenario.v_fic.id}",
        f"{BASE}/excel/presupuesto/{escenario.v_fic.id}",
    ):
        resp = c.get(ruta)
        assert resp.status_code == 200, resp.text
        wb = load_workbook(BytesIO(resp.content))
        celdas = [
            cell
            for ws in wb
            for row in ws.iter_rows()
            for cell in row
            if isinstance(cell.value, str) and "REV" in cell.value
        ]
        if "explosion" in ruta:
            assert celdas, "la descripción modificada debe aparecer en la exportación de explosión"
        for cell in celdas:
            assert cell.data_type == "s" and cell.value == descripcion, (ruta, cell.coordinate)


def test_asignar_celda_respeta_numeros_y_textos_normales() -> None:
    wb = xl.nuevo_libro()
    ws = wb.create_sheet("X")
    assert xl.asignar_celda(ws, 1, 1, -5).data_type == "n"
    assert xl.asignar_celda(ws, 1, 2, "Muro bloque").data_type == "s"
    c = xl.asignar_celda(ws, 1, 3, '=HYPERLINK("http://ejemplo.invalid")')
    assert c.data_type == "s"
    assert xl.es_texto_peligroso("\tx") and not xl.es_texto_peligroso("x=1")


# --- Rango Numeric(18,4) -----------------------------------------------------------------
def test_compromiso_con_valor_fuera_de_rango_responde_422(client_as, escenario: Escenario) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "presupuesto_id": escenario.presupuesto.id,
        "tipo": "ORDEN_COMPRA",
        "numero": "OC-RANGO",
        "fecha": "2026-09-15",
        "tercero": "Proveedor Demo S.A.S.",
        "lineas": [
            {"item_id": escenario.item_c.id, "cantidad": "90000000000000", "valor_unitario": "90000000000000"}
        ],
    }
    r = client_as("obra").post(f"{BASE}/compromisos", json=payload)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "BUSINESS_RULE"
