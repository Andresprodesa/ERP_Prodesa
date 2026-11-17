"""Excel (§5.5): plantilla, importación (todo o nada) y exportaciones, incluido round-trip."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.core.models import AuditLog
from app.modules.adpro.control import excel as xl
from app.modules.adpro.control import service
from app.modules.adpro.enums import OrigenValor, TipoVersion
from app.modules.adpro.models import PresupuestoLinea
from tests.adpro.control.conftest import Escenario, nueva_version

D = Decimal
BASE = "/api/adpro/control/excel"
XLSX = xl.XLSX_MEDIA_TYPE


def _wb(resp) -> Any:  # type: ignore[no-untyped-def]
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == XLSX
    assert resp.headers["content-disposition"].startswith("attachment; filename=")
    return load_workbook(BytesIO(resp.content))


def _plantilla(
    filas: list[tuple[Any, ...]], encabezados: tuple[str, ...] = xl.ENCABEZADOS_PLANTILLA
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = xl.HOJA_PLANTILLA
    ws.append(list(encabezados))
    for f in filas:
        ws.append(list(f))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _importar(c, version_id: int, contenido: bytes, modo: str = "agregar"):  # type: ignore[no-untyped-def]
    return c.post(
        f"{BASE}/presupuesto/{version_id}/importar",
        params={"modo": modo},
        files={"file": ("presupuesto.xlsx", contenido, XLSX)},
    )


def _lineas(db, version_id: int) -> dict[str, PresupuestoLinea]:  # type: ignore[no-untyped-def]
    db.expire_all()
    return {
        ln.item.codigo: ln
        for ln in db.scalars(select(PresupuestoLinea).where(PresupuestoLinea.version_id == version_id))
    }


# --- Plantilla -----------------------------------------------------------------------------
def test_plantilla(client_as, escenario: Escenario) -> None:
    wb = _wb(client_as("consulta").get(f"{BASE}/plantilla-presupuesto"))
    assert {"Presupuesto", "Items", "Instrucciones"} <= set(wb.sheetnames)
    ws = wb["Presupuesto"]
    assert tuple(c.value for c in ws[1]) == xl.ENCABEZADOS_PLANTILLA
    assert ws.max_row == 1 and ws["A1"].font.bold
    items = {r[0]: r for r in wb["Items"].iter_rows(min_row=2, values_only=True)}
    assert items["01.01.001.0001"][3] == "SI" and items["02.01.001.0001"][3] == "NO"
    assert len(items) == 4


# --- Exportaciones -------------------------------------------------------------------------
def test_exportar_presupuesto(client_as, escenario: Escenario, db) -> None:
    wb = _wb(client_as("consulta").get(f"{BASE}/presupuesto/{escenario.v_fic.id}"))
    assert wb.sheetnames == ["Resumen", "Presupuesto"]
    ws = wb["Presupuesto"]
    header = [c.value for c in ws[1]]
    assert tuple(header[:6]) == xl.ENCABEZADOS_PLANTILLA  # re-importable
    assert ws["A1"].font.bold and ws.freeze_panes == "A2"
    filas = list(ws.iter_rows(min_row=2, values_only=True))
    assert [f[0] for f in filas[:3]] == ["01.01.001.0001", "01.01.001.0002", "02.01.001.0001"]
    assert filas[0][3] == 100 and filas[0][4] == 12100 and filas[0][6] == 1210000 and filas[0][8] == "APU"
    assert filas[2][8] == "MANUAL"
    assert len(filas) == 3  # sin fila TOTAL: re-importable tal cual
    assert ws.cell(row=2, column=7).number_format == "#,##0"
    assert ws.cell(row=2, column=5).number_format == "#,##0.00"

    res = {r[0]: r[1] for r in wb["Resumen"].iter_rows(values_only=True) if r and r[0]}
    assert res["Costo directo"] == 1860000
    # A 8% = 148.800 ; I 2% = 37.200 ; U 5% = 93.000 ; IVA 19% U = 17.670
    assert res["TOTAL PRESUPUESTO"] == 1860000 + 148800 + 37200 + 93000 + 17670
    assert res["01"] == "Preliminares"
    assert db.scalars(select(AuditLog).where(AuditLog.accion == "EXPORTAR")).first() is not None


def test_exportar_explosion(client_as, escenario: Escenario) -> None:
    wb = _wb(client_as("consulta").get(f"{BASE}/explosion/{escenario.v_fic.id}"))
    assert wb.sheetnames == ["Explosion", "PorTipo"]
    filas = {r[0]: r for r in wb["Explosion"].iter_rows(min_row=2, values_only=True)}
    assert filas["MAT-001"][4] == 210 and filas["MAT-001"][6] == 210000 and filas["MAT-001"][3] == "MAT"
    assert filas["MO-001"][6] == 1000000
    assert filas["TOTAL INSUMOS"][6] == 1260000
    tipos = {r[0]: r for r in wb["PorTipo"].iter_rows(values_only=True) if r and r[0]}
    assert tipos["MAT"][1] == 260000 and tipos["MO"][1] == 1000000
    assert tipos["Valor sin desglose (líneas manuales/importadas)"][1] == 600000
    assert tipos["Total costo directo"][1] == 1860000
    assert wb["PorTipo"]["C2"].number_format == "0.00%"


def test_exportar_comparativo(client_as, escenario: Escenario) -> None:
    c = client_as("consulta")
    params = {"version_base_id": escenario.v_fic.id, "version_comparada_id": escenario.v_fiv.id}
    wb = _wb(c.get(f"{BASE}/comparativo", params=params))
    ws = wb["Comparativo"]
    filas = list(ws.iter_rows(values_only=True))
    hdr = next(i for i, f in enumerate(filas) if f[0] == "Código")
    datos = {f[0]: f for f in filas[hdr + 1 :]}
    assert datos["01.01.001.0002"][13] == 10000 and datos["01.01.001.0002"][15] == "MODIFICADO"
    assert datos["TOTAL"][9] == 1860000 and datos["TOTAL"][13] == -585000
    wb = _wb(c.get(f"{BASE}/comparativo", params={**params, "nivel": "insumo"}))
    assert any(r[0] == "MAT-001" for r in wb["Comparativo"].iter_rows(values_only=True))
    assert c.get(f"{BASE}/presupuesto/99999").status_code == 404


# --- Importación ---------------------------------------------------------------------------
def test_round_trip_exportar_importar(client_as, escenario: Escenario, db) -> None:
    c = client_as("presupuesto")
    exportado = c.get(f"{BASE}/presupuesto/{escenario.v_fic.id}").content

    destino = nueva_version(db, escenario.presupuesto, 7, TipoVersion.OTRO)
    db.commit()
    r = _importar(c, destino.id, exportado)  # el archivo exportado se importa sin tocarlo
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aplicado"] is True and body["lineas_creadas"] == 3 and body["errores"] == []
    lineas = _lineas(db, destino.id)
    assert all(ln.origen_unitario is OrigenValor.IMPORTADO for ln in lineas.values())

    comp = service.comparar_versiones(db, escenario.v_fic.id, destino.id, "item")
    assert {f.estado for f in comp.filas} == {"IGUAL"}
    assert comp.totales.impacto == 0

    # Y de vuelta: exportar la importada produce las mismas filas de datos
    wb2 = load_workbook(BytesIO(c.get(f"{BASE}/presupuesto/{destino.id}").content))
    orig = [r[:7] for r in load_workbook(BytesIO(exportado))["Presupuesto"].iter_rows(values_only=True)]
    nuevo = [r[:7] for r in wb2["Presupuesto"].iter_rows(values_only=True)]
    assert orig == nuevo
    log = db.scalars(select(AuditLog).where(AuditLog.accion == "IMPORTAR")).all()
    assert len(log) == 1 and log[0].entidad_id == str(destino.id)


def test_importar_desde_apu_genera_snapshot(client_as, escenario: Escenario, db) -> None:
    c = client_as("admin")
    destino = nueva_version(db, escenario.presupuesto, 8, TipoVersion.OTRO)
    db.commit()
    contenido = _plantilla(
        [
            ("01.01.001.0001", "Item A demo", "M2", 10, None, "desde APU"),
            ("02.01.001.0001", None, "UN", "1.250,5", "1000", None),
        ]
    )
    body = _importar(c, destino.id, contenido).json()
    assert body["aplicado"] is True and body["lineas_creadas"] == 2
    assert any("unidad 'UN'" in a for a in body["advertencias"])
    lineas = _lineas(db, destino.id)
    a = lineas["01.01.001.0001"]
    assert (
        a.origen_unitario is OrigenValor.APU
        and a.valor_unitario == D("12100")
        and a.valor_total == D("121000")
    )
    assert len(a.insumos) == 2 and a.observacion == "desde APU"
    cc = lineas["02.01.001.0001"]
    assert cc.cantidad == D("1250.5") and cc.valor_total == D("1250500") and cc.insumos == []


def test_importar_agregar_actualiza_y_reemplazar(client_as, escenario: Escenario, db) -> None:
    c = client_as("presupuesto")
    v = escenario.v_fiv  # A 100, B 12, D 5
    body = _importar(c, v.id, _plantilla([("01.01.001.0001", None, None, 50, None, None)])).json()
    assert (body["lineas_creadas"], body["lineas_actualizadas"]) == (0, 1)
    lineas = _lineas(db, v.id)
    assert lineas["01.01.001.0001"].cantidad == D("50") and len(lineas["01.01.001.0001"].insumos) == 2
    assert len(lineas) == 3

    body = _importar(
        c, v.id, _plantilla([("01.01.001.0002", None, None, 3, "7000", None)]), "reemplazar"
    ).json()
    assert (body["lineas_creadas"], body["lineas_eliminadas"]) == (1, 3)
    lineas = _lineas(db, v.id)
    assert list(lineas) == ["01.01.001.0002"]
    assert lineas["01.01.001.0002"].origen_unitario is OrigenValor.IMPORTADO
    assert lineas["01.01.001.0002"].valor_total == D("21000")


def test_importar_todo_o_nada(client_as, escenario: Escenario, db) -> None:
    c = client_as("presupuesto")
    v = escenario.v_fiv
    antes = {k: (x.cantidad, x.valor_total) for k, x in _lineas(db, v.id).items()}
    contenido = _plantilla(
        [
            ("01.01.001.0001", None, None, 1, None, None),  # válida
            ("99.99.999.9999", None, None, 1, "1", None),  # no existe
            ("01", None, None, 1, "1", None),  # no es ITEM
            ("01.01.001.0002", None, None, -5, "1", None),  # cantidad negativa
            ("02.01.001.0001", None, None, "abc", "1", None),  # cantidad no numérica
            ("02.01.001.0002", None, None, 1, None, None),  # sin APU y sin valor
            ("01.01.001.0001", None, None, 2, "x", None),  # repetido + valor no numérico
            (None, "solo descripción", None, 1, "1", None),  # código vacío
            ("01.01.001.0002", None, None, None, "1", None),  # cantidad vacía (y repetido)
        ]
    )
    body = _importar(c, v.id, contenido, "reemplazar").json()
    assert body["aplicado"] is False and body["lineas_creadas"] == 0
    errs = {(e["fila"], e["columna"]) for e in body["errores"]}
    assert {
        (3, "codigo_item"),
        (4, "codigo_item"),
        (5, "cantidad"),
        (6, "cantidad"),
        (7, "valor_unitario"),
        (8, "codigo_item"),
        (8, "valor_unitario"),
        (9, "codigo_item"),
        (10, "cantidad"),
    } <= errs
    assert (2, "codigo_item") not in errs
    despues = {k: (x.cantidad, x.valor_total) for k, x in _lineas(db, v.id).items()}
    assert despues == antes


def test_importar_estructura_invalida(client_as, escenario: Escenario) -> None:
    c = client_as("presupuesto")
    v = escenario.v_fiv
    r = _importar(c, v.id, b"esto no es un excel")
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    body = _importar(c, v.id, _plantilla([], encabezados=("codigo", "cantidad"))).json()
    assert body["aplicado"] is False and body["errores"][0]["fila"] == 1
    body = _importar(c, v.id, _plantilla([])).json()
    assert body["aplicado"] is False and "no tiene filas" in body["errores"][0]["mensaje"]
    wb = Workbook()
    wb.active.title = "Otra"
    buf = BytesIO()
    wb.save(buf)
    body = _importar(c, v.id, buf.getvalue()).json()
    assert "No existe la hoja" in body["errores"][0]["mensaje"]
    r = c.post(
        f"{BASE}/presupuesto/{v.id}/importar",
        params={"modo": "otro"},
        files={"file": ("p.xlsx", _plantilla([]), XLSX)},
    )
    assert r.status_code == 422


def test_importar_reglas_y_roles(client_as, escenario: Escenario) -> None:
    contenido = _plantilla([("01.01.001.0001", None, None, 1, "1", None)])
    r = _importar(client_as("admin"), escenario.v_fic.id, contenido)  # APROBADA
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    assert _importar(client_as("admin"), 99999, contenido).status_code == 404
    assert _importar(client_as("obra"), escenario.v_fiv.id, contenido).status_code == 403
    assert _importar(client_as("consulta"), escenario.v_fiv.id, contenido).status_code == 403


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (None, None),
        ("", None),
        (5, D("5")),
        (2.5, D("2.5")),
        ("1250.5", D("1250.5")),
        ("1.250,5", D("1250.5")),
        ("$ 1.000", D("1000")),
        ("1.234.567", D("1234567")),
        (D("3.3"), D("3.3")),
    ],
)
def test_parse_decimal(valor: Any, esperado: Decimal | None) -> None:
    assert xl.parse_decimal(valor) == esperado


@pytest.mark.parametrize("valor", ["abc", True, "NaN"])
def test_parse_decimal_invalido(valor: Any) -> None:
    with pytest.raises(ValueError):
        xl.parse_decimal(valor)
