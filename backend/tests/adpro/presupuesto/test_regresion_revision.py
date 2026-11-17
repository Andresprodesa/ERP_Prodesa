"""Regresiones de la revisión de dominio y arquitectura sobre presupuesto (números a mano).

Cada test corresponde a un hallazgo corregido:
- Inmutabilidad: la explosión por tipo de una versión APROBADA no cambia al editar el maestro
  (el tipo de un insumo usado en versiones aprobadas ya no se puede cambiar).
- Explosión: se valoriza con la cantidad EXACTA (antes q4) y cuadra con el costo directo.
- Guardia ORM: APROBADO solo puede pasar a CERRADO (antes aceptaba volver a BORRADOR).
- APU inactivo: recalcular/copiar no revalorizan con él (antes sí).
- Concurrencia (TOCTOU): una edición iniciada en BORRADOR no se guarda si otro usuario aprobó.
- Rangos: valores que no caben en Numeric(18,4) o int32 responden 422 (antes 500 en PostgreSQL).

Datos 100 % SINTÉTICOS (escenario de ``tests/adpro/apu/escenario.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import BusinessRuleError
from app.modules.adpro.control import excel as xl
from app.modules.adpro.enums import EstadoVersion, NivelEdt, TipoInsumo
from app.modules.adpro.models import (
    Apu,
    ApuInsumo,
    EdtNodo,
    Insumo,
    PrecioInsumo,
    PresupuestoLinea,
    PresupuestoVersion,
    Unidad,
)
from app.modules.adpro.presupuesto import service as presupuesto_service

D = Decimal
BASE = "/api/adpro/presupuestos"
CONTROL = "/api/adpro/control"


@pytest.fixture()
def nueva_version(auth_client: TestClient, esc: dict[str, int]) -> Callable[..., dict[str, Any]]:
    """Presupuesto + versión BORRADOR (precios 2026-03-01 BOG, A8 % I2 % U5 % IVA19 %)."""

    def _crear(lineas: list[dict[str, Any]] | None = None, codigo: str = "rev-01") -> dict[str, Any]:
        p = auth_client.post(
            BASE, json={"proyecto_id": esc["proyecto"], "codigo": codigo, "nombre": "Ppto revision"}
        )
        assert p.status_code == 201, p.text
        pid = p.json()["id"]
        v = auth_client.post(
            f"{BASE}/{pid}/versiones",
            json={
                "tipo": "FIC",
                "nombre": "FIC revision",
                "fecha_precios": "2026-03-01",
                "administracion_pct": "0.08",
                "imprevistos_pct": "0.02",
                "utilidad_pct": "0.05",
                "iva_utilidad_pct": "0.19",
            },
        )
        assert v.status_code == 201, v.text
        vid = v.json()["id"]
        if lineas:
            r = auth_client.post(f"{BASE}/versiones/{vid}/lineas/lote", json={"lineas": lineas})
            assert r.status_code == 200 and r.json()["errores"] == [], r.text
        return {"pid": pid, "vid": vid}

    return _crear


def _aprobar(client: TestClient, vid: int) -> None:
    r = client.post(f"{BASE}/versiones/{vid}/aprobar", json={})
    assert r.status_code == 200, r.text


# =====================================================================================
# Cálculos verificados a mano (guardas)
# =====================================================================================
def test_aiu_iva_sobre_utilidad_a_mano(auth_client, esc, nueva_version) -> None:  # type: ignore[no-untyped-def]
    """Muro 100.5*12100 = 1 216 050; Concreto 12.35*393416.664 = 4 858 695.80 -> 4 858 696;
    Losa 3.3*85000.5 = 280 501.65 -> 280 502.  CD = 6 355 248.
    A 8 % = 508 420; I 2 % = 127 105; U 5 % = 317 762; IVA 19 % s/U = 60 375.  Total = 7 368 910."""
    ids = nueva_version(
        [
            {"item_id": esc["muro"], "cantidad": "100.5"},
            {"item_id": esc["concreto"], "cantidad": "12.35"},
            {"item_id": esc["losa"], "cantidad": "3.3", "valor_unitario": "85000.5"},
        ]
    )
    r = auth_client.get(f"{BASE}/versiones/{ids['vid']}/resumen").json()
    assert (D(r["costo_directo"]), D(r["administracion"]), D(r["imprevistos"])) == (
        D("6355248"),
        D("508420"),
        D("127105"),
    )
    assert (D(r["utilidad"]), D(r["iva_utilidad"]), D(r["total"])) == (D("317762"), D("60375"), D("7368910"))
    # La explosión (cantidades exactas) cuadra con el costo directo
    e = auth_client.get(f"{BASE}/versiones/{ids['vid']}/explosion").json()
    assert D(e["total"]) == D(r["costo_directo"])


def test_versiones_aprobadas_inmutables_por_todos_los_endpoints(auth_client, esc, nueva_version) -> None:  # type: ignore[no-untyped-def]
    ids = nueva_version([{"item_id": esc["muro"], "cantidad": "10"}])
    vid = ids["vid"]
    _aprobar(auth_client, vid)
    lid = auth_client.get(f"{BASE}/versiones/{vid}/lineas").json()[0]["id"]
    wb = Workbook()
    ws = wb.active
    ws.title = xl.HOJA_PLANTILLA
    ws.append(list(xl.ENCABEZADOS_PLANTILLA))
    ws.append(["01.01.001.0001", None, None, 5, None, None])
    buf = BytesIO()
    wb.save(buf)
    intentos = [
        auth_client.put(f"{BASE}/versiones/{vid}", json={"utilidad_pct": "0.5"}),
        auth_client.post(
            f"{BASE}/versiones/{vid}/lineas",
            json={"item_id": esc["losa"], "cantidad": "1", "valor_unitario": "1"},
        ),
        auth_client.post(
            f"{BASE}/versiones/{vid}/lineas/lote",
            json={"lineas": [{"item_id": esc["losa"], "cantidad": "1", "valor_unitario": "1"}]},
        ),
        auth_client.put(f"{BASE}/versiones/{vid}/lineas/{lid}", json={"cantidad": "99"}),
        auth_client.delete(f"{BASE}/versiones/{vid}/lineas/{lid}"),
        auth_client.post(f"{BASE}/versiones/{vid}/recalcular"),
        auth_client.delete(f"{BASE}/versiones/{vid}"),
        auth_client.post(
            f"{CONTROL}/excel/presupuesto/{vid}/importar",
            files={"file": ("p.xlsx", buf.getvalue(), xl.XLSX_MEDIA_TYPE)},
        ),
    ]
    for r in intentos:
        assert r.status_code in (409, 422) or (r.status_code == 200 and r.json().get("errores")), (
            r.request.method,
            r.request.url,
            r.status_code,
        )
    linea = auth_client.get(f"{BASE}/versiones/{vid}/lineas").json()
    assert len(linea) == 1 and D(linea[0]["cantidad"]) == 10 and D(linea[0]["valor_total"]) == 121000


# =====================================================================================
# Hallazgos corregidos
# =====================================================================================
def test_tipo_de_insumo_en_version_aprobada_no_se_puede_cambiar(auth_client, esc, nueva_version) -> None:  # type: ignore[no-untyped-def]
    """Muro 10 M2 a 2026-03: MAT = 10*2*1.05*1000 = 21 000, MO = 10*0.5*20000 = 100 000."""
    ids = nueva_version([{"item_id": esc["muro"], "cantidad": "10"}])
    url = f"{BASE}/versiones/{ids['vid']}/explosion"
    # En BORRADOR el maestro sigue mandando: se puede reclasificar y volver
    assert auth_client.put(f"/api/adpro/maestros/insumos/{esc['mo']}", json={"tipo": "EQ"}).status_code == 200
    assert auth_client.put(f"/api/adpro/maestros/insumos/{esc['mo']}", json={"tipo": "MO"}).status_code == 200
    _aprobar(auth_client, ids["vid"])
    antes = {t["tipo"]: D(t["valor_total"]) for t in auth_client.get(url).json()["por_tipo"]}
    assert antes == {"MAT": D("21000"), "MO": D("100000")}

    r = auth_client.put(f"/api/adpro/maestros/insumos/{esc['mo']}", json={"tipo": "EQ"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE", r.text
    # mismo tipo (sin cambio real) sí se acepta
    assert auth_client.put(f"/api/adpro/maestros/insumos/{esc['mo']}", json={"tipo": "MO"}).status_code == 200
    despues = {t["tipo"]: D(t["valor_total"]) for t in auth_client.get(url).json()["por_tipo"]}
    assert despues == antes


def test_unidad_de_insumo_en_uso_no_se_puede_cambiar(auth_client, esc, db: Session) -> None:  # type: ignore[no-untyped-def]
    un = db.scalar(select(Unidad).where(Unidad.codigo == "UN"))
    r = auth_client.put(f"/api/adpro/maestros/insumos/{esc['cem']}", json={"unidad_id": un.id})
    assert r.status_code == 422 and "unidad" in r.json()["error"]["message"], r.text


def test_explosion_valoriza_con_cantidad_exacta(  # type: ignore[no-untyped-def]
    auth_client, esc, nueva_version, db: Session
) -> None:
    """SUB ascensor 0.008333 UN a 185 000 000 -> APU = 1 541 605. Línea 37 UN -> 57 039 385.
    Explosión: cantidad mostrada q4(0.308321) = 0.3083; valor = 0.308321·185e6 = 57 039 385
    (antes 0.3083·185e6 = 57 035 500: 3 885 pesos de descuadre en una fila)."""
    un = db.scalar(select(Unidad).where(Unidad.codigo == "UN"))
    asc = Insumo(codigo="SUB-ASC", descripcion="Ascensor (demo)", unidad_id=un.id, tipo=TipoInsumo.SUB)
    db.add(asc)
    db.flush()
    db.add(PrecioInsumo(lista_id=esc["l1"], insumo_id=asc.id, precio=D("185000000")))
    item = EdtNodo(
        nivel=NivelEdt.ITEM,
        codigo="01.01.001.0009",
        descripcion="Ascensor por vivienda (demo)",
        parent_id=esc["grupo01"],
        unidad_id=un.id,
    )
    db.add(item)
    db.flush()
    apu = Apu(item_id=item.id, descripcion="APU ascensor demo")
    apu.insumos = [ApuInsumo(insumo_id=asc.id, cantidad=D("0.008333"), desperdicio_pct=D("0"), orden=1)]
    db.add(apu)
    db.commit()

    ids = nueva_version([{"item_id": item.id, "cantidad": "37"}])
    resumen = auth_client.get(f"{BASE}/versiones/{ids['vid']}/resumen").json()
    explosion = auth_client.get(f"{BASE}/versiones/{ids['vid']}/explosion").json()
    assert D(resumen["costo_directo"]) == D("57039385")
    fila = explosion["filas"][0]
    assert D(fila["cantidad_total"]) == D("0.3083")
    assert D(fila["valor_total"]) == D("57039385") == D(explosion["total"])
    # el detalle de insumos de la línea usa la misma regla
    lid = auth_client.get(f"{BASE}/versiones/{ids['vid']}/lineas").json()[0]["id"]
    det = auth_client.get(f"{BASE}/versiones/{ids['vid']}/lineas/{lid}/insumos").json()[0]
    assert D(det["cantidad_total"]) == D("0.3083") and D(det["valor_total"]) == D("57039385")


def test_guardia_orm_no_permite_devolver_aprobada_a_borrador(  # type: ignore[no-untyped-def]
    auth_client, esc, nueva_version, db: Session
) -> None:
    ids = nueva_version([{"item_id": esc["muro"], "cantidad": "10"}])
    _aprobar(auth_client, ids["vid"])
    v = db.get(PresupuestoVersion, ids["vid"])
    v.estado = EstadoVersion.BORRADOR
    with pytest.raises(BusinessRuleError):
        db.flush()
    db.rollback()
    # APROBADO -> CERRADO sí sigue permitido (por servicio)
    cerrada = presupuesto_service.cerrar_version(db, ids["vid"])
    assert cerrada.estado is EstadoVersion.CERRADO


def test_recalcular_y_copiar_no_usan_apu_inactivo(auth_client, esc, nueva_version, db: Session) -> None:  # type: ignore[no-untyped-def]
    """Muro 10 M2 = 121 000. Se inactiva el APU y se sube MO a 1 HR (con APU activo serían
    10·(2100 + 20000) = 221 000): recalcular y copiar conservan 121 000 y lo reportan."""
    ids = nueva_version([{"item_id": esc["muro"], "cantidad": "10"}])
    r = auth_client.put(f"/api/adpro/apu/apus/{esc['apu_muro']}", json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False, r.text
    comp = db.scalar(
        select(ApuInsumo).where(ApuInsumo.apu_id == esc["apu_muro"], ApuInsumo.insumo_id == esc["mo"])
    )
    comp.cantidad = D("1")
    db.commit()

    nueva = nueva_version(codigo="rev-x")
    r_crear = auth_client.post(
        f"{BASE}/versiones/{nueva['vid']}/lineas", json={"item_id": esc["muro"], "cantidad": "1"}
    )
    assert r_crear.status_code == 422, r_crear.text

    r = auth_client.post(f"{BASE}/versiones/{ids['vid']}/recalcular")
    assert r.status_code == 200, r.text
    assert r.json()["lineas_recalculadas"] == 0 and r.json()["items_sin_apu"] == [esc["muro"]]
    total = D(auth_client.get(f"{BASE}/versiones/{ids['vid']}/lineas").json()[0]["valor_total"])
    assert total == D("121000")

    copia = auth_client.post(
        f"{BASE}/versiones/{ids['vid']}/copiar",
        json={"tipo": "FIV", "nombre": "Copia", "recalcular_precios": True},
    )
    assert copia.status_code == 201, copia.text
    lineas = auth_client.get(f"{BASE}/versiones/{copia.json()['id']}/lineas").json()
    assert D(lineas[0]["valor_total"]) == D("121000")

    # al reactivar el APU sí revaloriza
    assert auth_client.put(f"/api/adpro/apu/apus/{esc['apu_muro']}", json={"activo": True}).status_code == 200
    r = auth_client.post(f"{BASE}/versiones/{ids['vid']}/recalcular").json()
    assert (
        r["lineas_recalculadas"] == 1
        and r["items_sin_apu"] == []
        and D(r["total_costo_directo"]) == D("221000")
    )


def test_edicion_concurrente_no_altera_version_aprobada(  # type: ignore[no-untyped-def]
    esc, nueva_version, session_factory: sessionmaker[Session]
) -> None:
    """A valida que la versión es editable y carga una línea; B aprueba en paralelo; A intenta
    guardar. La guardia relee el estado en la BD (FOR UPDATE en PostgreSQL) y lo rechaza."""
    vid = nueva_version([{"item_id": esc["muro"], "cantidad": "10"}])["vid"]
    with session_factory() as a, session_factory() as b:
        a.info["username"] = "usuario_a"
        b.info["username"] = "admin_b"
        v_a = presupuesto_service.obtener_version(a, vid)
        presupuesto_service.asegurar_editable(v_a)
        ln = a.scalars(select(PresupuestoLinea).where(PresupuestoLinea.version_id == vid)).first()
        assert ln is not None
        a.commit()  # A no retiene bloqueos mientras "piensa" (petición HTTP en curso)

        aprobada = presupuesto_service.aprobar_version(b, vid)
        total_congelado = aprobada.total_costo_directo

        ln.cantidad = ln.cantidad + D("1000")
        ln.valor_total = ln.valor_total + D("1000") * ln.valor_unitario
        with pytest.raises(BusinessRuleError):
            a.commit()
        a.rollback()

    with session_factory() as c:
        suma = c.scalar(
            select(func.sum(PresupuestoLinea.valor_total)).where(PresupuestoLinea.version_id == vid)
        )
        estado = c.get(PresupuestoVersion, vid).estado  # type: ignore[union-attr]
    assert estado is EstadoVersion.APROBADO
    assert suma == total_congelado == D("121000")


def test_valor_total_fuera_de_rango_se_rechaza_con_422(auth_client, esc, nueva_version) -> None:  # type: ignore[no-untyped-def]
    vid = nueva_version([{"item_id": esc["losa"], "cantidad": "1", "valor_unitario": "1000"}])["vid"]
    lid = auth_client.get(f"{BASE}/versiones/{vid}/lineas").json()[0]["id"]
    r = auth_client.put(
        f"{BASE}/versiones/{vid}/lineas/{lid}",
        json={"cantidad": "90000000000000", "valor_unitario": "90000000000000"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE", r.text
    r = auth_client.post(
        f"{BASE}/versiones/{vid}/lineas",
        json={"item_id": esc["panete"], "cantidad": "90000000000000", "valor_unitario": "2"},
    )
    assert r.status_code == 422, r.text
    linea = auth_client.get(f"{BASE}/versiones/{vid}/lineas").json()
    assert len(linea) == 1 and D(linea[0]["valor_total"]) == D("1000")


def test_orden_fuera_de_rango_int32_se_rechaza_con_422(auth_client, esc, nueva_version) -> None:  # type: ignore[no-untyped-def]
    vid = nueva_version([{"item_id": esc["losa"], "cantidad": "1", "valor_unitario": "1000"}])["vid"]
    lid = auth_client.get(f"{BASE}/versiones/{vid}/lineas").json()[0]["id"]
    r = auth_client.put(f"{BASE}/versiones/{vid}/lineas/{lid}", json={"orden": 99_999_999_999})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR", r.text
    assert auth_client.put(f"{BASE}/versiones/{vid}/lineas/{lid}", json={"orden": 7}).status_code == 200


def test_busqueda_de_presupuestos_escapa_comodines(auth_client, esc, nueva_version) -> None:  # type: ignore[no-untyped-def]
    nueva_version(codigo="rev-01")
    assert auth_client.get(BASE, params={"q": "_"}).json() == []
    assert auth_client.get(BASE, params={"q": "%"}).json() == []
    assert len(auth_client.get(BASE, params={"q": "REV-0"}).json()) == 1
