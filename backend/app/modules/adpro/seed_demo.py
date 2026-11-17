"""Datos de DEMOSTRACIÓN 100 % SINTÉTICOS del módulo ADPRO.

Lo invoca ``app.seed`` (``python -m app.seed``) después de crear usuarios, unidades y ciudades.
Ningún nombre, precio, tercero o proyecto corresponde a información real de Prodesa ni de
terceros: los precios son ficticios pero plausibles (COP 2026) para que la demo tenga sentido.

Contenido:
- Unidades adicionales (PTO) si faltan.
- ~70 insumos (MAT, MO, EQ, TR, SUB) y 4 listas de precios: Bogotá y Soacha, vigentes desde
  2026-01-01 y 2026-07-01 (histórico de precios).
- 2 proyectos ficticios: "Proyecto Demo Altos del Río" (VIS, Bogotá, 2 torres) y
  "Proyecto Demo Mirador" (NO_VIS, Soacha, 1 torre).
- EDT estilo ProdesaClass con 8 capítulos y 41 ítems, cada ítem con su APU.
- Presupuesto de Altos del Río: v1 BASE APROBADA (precios ene-2026, snapshot congelado) y
  v2 CONTROL en BORRADOR (precios jul-2026, cantidades ajustadas, un ítem nuevo MANUAL y uno
  eliminado) para mostrar el comparativo.
- Presupuesto de Mirador: v1 BASE en BORRADOR.
- 6 compromisos (uno ANULADO) y ejecución mensual de 3 periodos (2026-08 a 2026-10).

Idempotente: si ya existe el proyecto demo principal no hace nada y retorna 0.
Fórmulas SOLO vía ``app.modules.adpro.calculos`` y precios vía ``app.modules.adpro.valorizacion``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import Accion, registrar_auditoria
from app.modules.adpro.calculos import (
    calcular_aiu,
    redondear_pesos,
    valor_total_linea,
)
from app.modules.adpro.enums import (
    EstadoCompromiso,
    EstadoProyecto,
    EstadoVersion,
    NivelEdt,
    OrigenValor,
    TipoCompromiso,
    TipoInsumo,
    TipoProyecto,
    TipoVersion,
)
from app.modules.adpro.models import (
    Apu,
    ApuInsumo,
    Ciudad,
    Compromiso,
    CompromisoLinea,
    EdtNodo,
    Ejecucion,
    Etapa,
    Insumo,
    ListaPrecios,
    PrecioInsumo,
    Presupuesto,
    PresupuestoLinea,
    PresupuestoLineaInsumo,
    PresupuestoVersion,
    Proyecto,
    Torre,
    Unidad,
)
from app.modules.adpro.valorizacion import valorizar_apu

D = Decimal
USUARIO_SEED = "seed"
PROYECTO_PRINCIPAL = "PD-ADR"

FECHA_LISTA_1 = date(2026, 1, 1)
FECHA_LISTA_2 = date(2026, 7, 1)
FECHA_PRECIOS_BASE = date(2026, 3, 1)
FECHA_PRECIOS_CONTROL = date(2026, 8, 1)

# AIU de demostración (fracciones)
AIU_DEMO = {
    "administracion_pct": D("0.07"),
    "imprevistos_pct": D("0.02"),
    "utilidad_pct": D("0.05"),
    "iva_utilidad_pct": D("0.19"),
}

UNIDADES_EXTRA = [("PTO", "Punto")]

# ---------------------------------------------------------------------------------------
# Insumos: (código, descripción, unidad, tipo, precio Bogotá vigente desde 2026-01-01)
# Precios FICTICIOS en COP, sin IVA.
# ---------------------------------------------------------------------------------------
_M, _O, _E, _T, _S = TipoInsumo.MAT, TipoInsumo.MO, TipoInsumo.EQ, TipoInsumo.TR, TipoInsumo.SUB

INSUMOS: list[tuple[str, str, str, TipoInsumo, int]] = [
    # Materiales
    ("MAT-001", "Concreto premezclado 3000 psi (21 MPa)", "M3", _M, 520000),
    ("MAT-002", "Concreto premezclado 4000 psi (28 MPa)", "M3", _M, 575000),
    ("MAT-003", "Concreto pobre 1500 psi para solados", "M3", _M, 410000),
    ("MAT-004", "Acero de refuerzo 60.000 psi figurado", "KG", _M, 4600),
    ("MAT-005", "Malla electrosoldada para losa", "M2", _M, 18500),
    ("MAT-006", "Alambre negro calibre 18", "KG", _M, 7800),
    ("MAT-007", "Cemento gris de uso general (bulto 50 kg)", "BTO", _M, 34500),
    ("MAT-008", "Arena de pega", "M3", _M, 95000),
    ("MAT-009", "Arena lavada de río", "M3", _M, 110000),
    ("MAT-010", 'Gravilla triturada 3/4"', "M3", _M, 120000),
    ("MAT-011", "Agua para obra", "M3", _M, 6500),
    ("MAT-012", "Bloque de concreto 12x20x40 cm", "UN", _M, 2900),
    ("MAT-013", "Ladrillo de arcilla con perforación vertical 12x20x40 cm", "UN", _M, 2300),
    ("MAT-014", "Mortero seco de pega (bulto 40 kg)", "BTO", _M, 19500),
    ("MAT-015", "Mortero de relleno (grout) premezclado", "M3", _M, 480000),
    ("MAT-016", 'Tubería PVC sanitaria 4"', "ML", _M, 23500),
    ("MAT-017", 'Tubería PVC sanitaria 2"', "ML", _M, 9800),
    ("MAT-018", 'Tubería PVC presión 1/2" RDE 13.5', "ML", _M, 3900),
    ("MAT-019", 'Tubería CPVC agua caliente 1/2"', "ML", _M, 7600),
    ("MAT-020", "Accesorios PVC por punto (codos, tees, adaptadores)", "UN", _M, 8500),
    ("MAT-021", 'Tubo conduit PVC 1/2"', "ML", _M, 2400),
    ("MAT-022", "Cable de cobre THHN No. 12", "ML", _M, 3100),
    ("MAT-023", "Cable de cobre THHN No. 10", "ML", _M, 4700),
    ("MAT-024", "Caja de paso PVC 2x4", "UN", _M, 1200),
    ("MAT-025", "Tablero de distribución 8 circuitos", "UN", _M, 185000),
    ("MAT-026", "Aparato eléctrico estándar (toma o interruptor)", "UN", _M, 9800),
    ("MAT-027", "Baldosa cerámica 45x45 cm tráfico 4", "M2", _M, 32000),
    ("MAT-028", "Pegante cerámico (bulto 25 kg)", "BTO", _M, 22000),
    ("MAT-029", "Boquilla para cerámica", "KG", _M, 4300),
    ("MAT-030", "Estuco plástico listo para aplicar", "GAL", _M, 28000),
    ("MAT-031", "Pintura vinilo tipo 1 interior", "GAL", _M, 52000),
    ("MAT-032", "Sanitario de porcelana línea económica", "UN", _M, 245000),
    ("MAT-033", "Lavamanos de colgar con grifería", "UN", _M, 185000),
    ("MAT-034", "Puerta entamborada 0.80 m con marco metálico", "UN", _M, 385000),
    ("MAT-035", "Ventanería en aluminio con vidrio 4 mm", "M2", _M, 215000),
    ("MAT-036", "Recebo compactable (base granular)", "M3", _M, 78000),
    ("MAT-037", "Adoquín de concreto peatonal 20x10x6 cm", "M2", _M, 48000),
    ("MAT-038", "Bordillo prefabricado de concreto", "ML", _M, 36000),
    ("MAT-039", "Geotextil no tejido", "M2", _M, 4800),
    ("MAT-040", "Impermeabilizante cementicio", "KG", _M, 6200),
    ("MAT-041", "Lámina de zinc para cerramiento provisional", "M2", _M, 27000),
    ("MAT-042", 'Varenga de madera 2x4" para cerramiento', "ML", _M, 6800),
    # Mano de obra
    ("MO-001", "Cuadrilla oficial + ayudante", "DIA", _O, 285000),
    ("MO-002", "Cuadrilla oficial + 2 ayudantes", "DIA", _O, 395000),
    ("MO-003", "Oficial de mampostería", "DIA", _O, 135000),
    ("MO-004", "Ayudante de obra", "DIA", _O, 95000),
    ("MO-005", "Cuadrilla de armadores (oficial + ayudante)", "DIA", _O, 300000),
    ("MO-006", "Cuadrilla de enchape", "DIA", _O, 290000),
    ("MO-007", "Cuadrilla de pintura", "DIA", _O, 260000),
    ("MO-008", "Cuadrilla instaladora hidrosanitaria", "DIA", _O, 310000),
    ("MO-009", "Cuadrilla instaladora eléctrica", "DIA", _O, 320000),
    ("MO-010", "Comisión de topografía (topógrafo + cadenero)", "DIA", _O, 420000),
    # Equipos
    ("EQ-001", "Retroexcavadora sobre llantas con operador", "HR", _E, 165000),
    ("EQ-002", "Vibrador para concreto", "DIA", _E, 55000),
    ("EQ-003", "Mezcladora de concreto 1 bulto", "DIA", _E, 65000),
    ("EQ-004", "Formaleta metálica muro-losa (alquiler por uso)", "M2", _E, 14500),
    ("EQ-005", "Andamio tubular (sección)", "DIA", _E, 4500),
    ("EQ-006", "Herramienta menor", "DIA", _E, 12000),
    ("EQ-007", "Vibrocompactador tipo rana", "DIA", _E, 120000),
    ("EQ-008", "Bomba de concreto estacionaria (servicio por m3)", "M3", _E, 38000),
    ("EQ-009", "Estación total de topografía", "DIA", _E, 150000),
    ("EQ-010", "Torre grúa (alquiler mensual con operador)", "MES", _E, 28000000),
    # Transporte
    ("TR-001", "Volqueta 7 m3 (viaje)", "VJE", _T, 280000),
    ("TR-002", "Transporte interno de materiales (viaje)", "VJE", _T, 120000),
    ("TR-003", "Disposición de escombros en sitio autorizado", "M3", _T, 52000),
    # Subcontratos
    ("SUB-001", "Subcontrato pilote preexcavado D=0.40 m", "ML", _S, 185000),
    ("SUB-002", "Subcontrato impermeabilización de cubierta", "M2", _S, 48000),
    ("SUB-003", "Subcontrato red de gas natural por punto", "PTO", _S, 380000),
    ("SUB-004", "Subcontrato baranda metálica", "ML", _S, 165000),
    ("SUB-005", "Subcontrato aseo final de obra", "M2", _S, 4500),
    ("SUB-006", "Subcontrato red contra incendio por gabinete", "UN", _S, 4200000),
]

# Incremento de la lista de julio frente a la de enero, por tipo (ficticio) + excepciones.
INCREMENTO_JULIO = {_M: D("0.045"), _O: D("0"), _E: D("0.03"), _T: D("0.03"), _S: D("0.04")}
INCREMENTO_JULIO_INSUMO = {"MAT-004": D("0.08"), "MAT-001": D("0.06")}
FACTOR_SOACHA = D("0.98")

# ---------------------------------------------------------------------------------------
# EDT + APU. Item = (descripción, unidad, [(insumo, cantidad por unidad, desperdicio)],
#                    cantidad Altos del Río, cantidad Mirador)
# ---------------------------------------------------------------------------------------
Comp = tuple[str, str, str]
Item = tuple[str, str, list[Comp], str, str]

EDT: list[tuple[str, list[tuple[str, list[tuple[str, list[Item]]]]]]] = [
    (
        "PRELIMINARES",
        [
            (
                "Obras preliminares",
                [
                    (
                        "Localización, descapote y cerramiento",
                        [
                            (
                                "Localización y replanteo con equipo de precisión",
                                "M2",
                                [("MO-010", "0.004", "0"), ("EQ-009", "0.004", "0")],
                                "4200",
                                "2600",
                            ),
                            (
                                "Descapote y limpieza manual e=0.20 m",
                                "M2",
                                [("MO-001", "0.020", "0"), ("EQ-006", "0.020", "0")],
                                "4500",
                                "2800",
                            ),
                            (
                                "Cerramiento provisional en lámina de zinc h=2.10 m",
                                "ML",
                                [
                                    ("MAT-041", "2.1", "0.05"),
                                    ("MAT-042", "3.5", "0.05"),
                                    ("MO-001", "0.08", "0"),
                                ],
                                "620",
                                "410",
                            ),
                            (
                                "Retiro de sobrantes en volqueta",
                                "M3",
                                [("TR-001", "0.143", "0"), ("EQ-001", "0.05", "0")],
                                "1800",
                                "1100",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "CIMENTACIÓN",
        [
            (
                "Excavaciones y rellenos",
                [
                    (
                        "Movimiento de tierras",
                        [
                            (
                                "Excavación mecánica en material común",
                                "M3",
                                [("EQ-001", "0.08", "0"), ("MO-004", "0.05", "0"), ("TR-001", "0.15", "0")],
                                "2600",
                                "1500",
                            ),
                            (
                                "Relleno compactado con recebo",
                                "M3",
                                [("MAT-036", "1", "0.15"), ("EQ-007", "0.08", "0"), ("MO-001", "0.08", "0")],
                                "650",
                                "380",
                            ),
                        ],
                    ),
                ],
            ),
            (
                "Concretos de cimentación",
                [
                    (
                        "Pilotes, solados y estructura de cimentación",
                        [
                            (
                                "Solado en concreto pobre e=0.05 m",
                                "M2",
                                [("MAT-003", "0.05", "0.05"), ("MO-001", "0.02", "0")],
                                "1500",
                                "900",
                            ),
                            ("Pilote preexcavado D=0.40 m", "ML", [("SUB-001", "1", "0")], "1800", "1000"),
                            (
                                "Concreto 4000 psi para dados y vigas de cimentación",
                                "M3",
                                [
                                    ("MAT-002", "1", "0.03"),
                                    ("EQ-008", "1", "0"),
                                    ("EQ-002", "0.1", "0"),
                                    ("MO-002", "0.25", "0"),
                                ],
                                "420",
                                "260",
                            ),
                            (
                                "Acero de refuerzo para cimentación",
                                "KG",
                                [
                                    ("MAT-004", "1", "0.05"),
                                    ("MAT-006", "0.015", "0"),
                                    ("MO-005", "0.0045", "0"),
                                ],
                                "52000",
                                "31000",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "ESTRUCTURA",
        [
            (
                "Estructura en concreto",
                [
                    (
                        "Sistema industrializado muro-losa",
                        [
                            (
                                "Concreto 3000 psi para muros estructurales",
                                "M3",
                                [
                                    ("MAT-001", "1", "0.03"),
                                    ("EQ-008", "1", "0"),
                                    ("EQ-002", "0.08", "0"),
                                    ("MO-002", "0.20", "0"),
                                ],
                                "2100",
                                "1200",
                            ),
                            (
                                "Concreto 3000 psi para losas e=0.10 m",
                                "M3",
                                [
                                    ("MAT-001", "1", "0.03"),
                                    ("EQ-008", "1", "0"),
                                    ("EQ-002", "0.08", "0"),
                                    ("MO-002", "0.18", "0"),
                                ],
                                "1650",
                                "950",
                            ),
                            (
                                "Formaleta metálica muro-losa",
                                "M2",
                                [("EQ-004", "1", "0"), ("MO-002", "0.012", "0")],
                                "36000",
                                "21000",
                            ),
                            (
                                "Malla electrosoldada para losas",
                                "M2",
                                [("MAT-005", "1", "0.08"), ("MO-005", "0.006", "0")],
                                "16500",
                                "9500",
                            ),
                            (
                                "Acero de refuerzo para estructura",
                                "KG",
                                [
                                    ("MAT-004", "1", "0.05"),
                                    ("MAT-006", "0.015", "0"),
                                    ("MO-005", "0.0045", "0"),
                                ],
                                "145000",
                                "84000",
                            ),
                            ("Torre grúa (alquiler mensual)", "MES", [("EQ-010", "1", "0")], "10", "7"),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "MAMPOSTERÍA",
        [
            (
                "Muros no estructurales y fachadas",
                [
                    (
                        "Muros y pañetes",
                        [
                            (
                                "Muro en bloque de concreto 12x20x40 cm",
                                "M2",
                                [
                                    ("MAT-012", "12.5", "0.05"),
                                    ("MAT-014", "0.22", "0.05"),
                                    ("MO-001", "0.09", "0"),
                                ],
                                "5200",
                                "2600",
                            ),
                            (
                                "Muro en ladrillo de arcilla perforación vertical",
                                "M2",
                                [
                                    ("MAT-013", "12.5", "0.05"),
                                    ("MAT-014", "0.25", "0.05"),
                                    ("MO-001", "0.10", "0"),
                                ],
                                "2400",
                                "2200",
                            ),
                            (
                                "Dintel y columneta en concreto reforzado",
                                "ML",
                                [
                                    ("MAT-001", "0.018", "0.05"),
                                    ("MAT-004", "2.2", "0.05"),
                                    ("MO-001", "0.04", "0"),
                                ],
                                "3100",
                                "1700",
                            ),
                            (
                                "Pañete impermeabilizado para fachada",
                                "M2",
                                [
                                    ("MAT-007", "0.30", "0.05"),
                                    ("MAT-008", "0.025", "0.10"),
                                    ("MAT-040", "1.5", "0.05"),
                                    ("MO-001", "0.07", "0"),
                                ],
                                "3800",
                                "2300",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "INSTALACIONES HIDROSANITARIAS",
        [
            (
                "Redes internas",
                [
                    (
                        "Redes hidráulicas",
                        [
                            (
                                'Punto hidráulico agua fría PVC 1/2"',
                                "PTO",
                                [("MAT-018", "6", "0.05"), ("MAT-020", "1", "0"), ("MO-008", "0.08", "0")],
                                "1440",
                                "840",
                            ),
                            (
                                'Punto agua caliente CPVC 1/2"',
                                "PTO",
                                [("MAT-019", "6", "0.05"), ("MAT-020", "1", "0"), ("MO-008", "0.09", "0")],
                                "480",
                                "360",
                            ),
                        ],
                    ),
                    (
                        "Redes sanitarias y aparatos",
                        [
                            (
                                'Punto sanitario PVC 2"',
                                "PTO",
                                [("MAT-017", "3", "0.05"), ("MAT-020", "1", "0"), ("MO-008", "0.07", "0")],
                                "1200",
                                "720",
                            ),
                            (
                                'Bajante sanitaria PVC 4"',
                                "ML",
                                [("MAT-016", "1", "0.05"), ("MAT-020", "0.3", "0"), ("MO-008", "0.03", "0")],
                                "1100",
                                "640",
                            ),
                            (
                                "Suministro e instalación de aparatos sanitarios (juego)",
                                "UN",
                                [("MAT-032", "1", "0"), ("MAT-033", "1", "0"), ("MO-008", "0.25", "0")],
                                "240",
                                "120",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "INSTALACIONES ELÉCTRICAS Y GAS",
        [
            (
                "Redes eléctricas y de gas",
                [
                    (
                        "Salidas, acometidas y tableros",
                        [
                            (
                                "Salida eléctrica (toma o iluminación)",
                                "PTO",
                                [
                                    ("MAT-021", "8", "0.05"),
                                    ("MAT-022", "24", "0.05"),
                                    ("MAT-024", "1", "0"),
                                    ("MAT-026", "1", "0"),
                                    ("MO-009", "0.08", "0"),
                                ],
                                "5800",
                                "3600",
                            ),
                            (
                                "Acometida eléctrica en cable No. 10",
                                "ML",
                                [("MAT-023", "3", "0.03"), ("MAT-021", "1.05", "0"), ("MO-009", "0.02", "0")],
                                "2600",
                                "1500",
                            ),
                            (
                                "Tablero de distribución 8 circuitos",
                                "UN",
                                [("MAT-025", "1", "0"), ("MO-009", "0.25", "0")],
                                "240",
                                "120",
                            ),
                            ("Red de gas natural por punto", "PTO", [("SUB-003", "1", "0")], "240", "120"),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "ACABADOS",
        [
            (
                "Pisos y enchapes",
                [
                    (
                        "Cerámicas",
                        [
                            (
                                "Piso en cerámica 45x45 cm",
                                "M2",
                                [
                                    ("MAT-027", "1", "0.07"),
                                    ("MAT-028", "0.20", "0.05"),
                                    ("MAT-029", "0.30", "0.05"),
                                    ("MO-006", "0.06", "0"),
                                ],
                                "11500",
                                "8200",
                            ),
                            (
                                "Enchape de muros en baños",
                                "M2",
                                [
                                    ("MAT-027", "1", "0.10"),
                                    ("MAT-028", "0.22", "0.05"),
                                    ("MAT-029", "0.35", "0.05"),
                                    ("MO-006", "0.075", "0"),
                                ],
                                "4300",
                                "2600",
                            ),
                        ],
                    ),
                ],
            ),
            (
                "Pintura, carpintería y cubierta",
                [
                    (
                        "Pintura y carpinterías",
                        [
                            (
                                "Estuco y pintura vinilo tres manos",
                                "M2",
                                [
                                    ("MAT-030", "0.08", "0.05"),
                                    ("MAT-031", "0.07", "0.05"),
                                    ("MO-007", "0.025", "0"),
                                    ("EQ-005", "0.02", "0"),
                                ],
                                "38000",
                                "24000",
                            ),
                            (
                                "Puerta entamborada 0.80 m instalada",
                                "UN",
                                [("MAT-034", "1", "0"), ("MO-004", "0.25", "0")],
                                "960",
                                "480",
                            ),
                            (
                                "Ventanería en aluminio instalada",
                                "M2",
                                [("MAT-035", "1", "0.02"), ("MO-004", "0.05", "0")],
                                "2300",
                                "1500",
                            ),
                            (
                                "Impermeabilización de cubierta",
                                "M2",
                                [("SUB-002", "1", "0.05")],
                                "1450",
                                "800",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "URBANISMO",
        [
            (
                "Obras exteriores",
                [
                    (
                        "Andenes, zonas comunes y entrega",
                        [
                            (
                                "Andén en concreto 3000 psi e=0.10 m",
                                "M2",
                                [
                                    ("MAT-001", "0.10", "0.05"),
                                    ("MAT-036", "0.15", "0.15"),
                                    ("MO-001", "0.05", "0"),
                                    ("EQ-007", "0.02", "0"),
                                ],
                                "2800",
                                "1600",
                            ),
                            (
                                "Adoquín peatonal sobre base granular",
                                "M2",
                                [
                                    ("MAT-037", "1", "0.03"),
                                    ("MAT-009", "0.04", "0.10"),
                                    ("MAT-036", "0.20", "0.15"),
                                    ("MAT-039", "1", "0.05"),
                                    ("MO-001", "0.06", "0"),
                                    ("EQ-007", "0.03", "0"),
                                ],
                                "1900",
                                "1200",
                            ),
                            (
                                "Bordillo prefabricado de concreto",
                                "ML",
                                [("MAT-038", "1", "0.02"), ("MAT-007", "0.05", "0"), ("MO-001", "0.03", "0")],
                                "1200",
                                "700",
                            ),
                            ("Baranda metálica", "ML", [("SUB-004", "1", "0")], "450", "320"),
                            ("Aseo final de obra", "M2", [("SUB-005", "1", "0")], "18000", "11000"),
                            (
                                "Retiro de escombros a sitio autorizado",
                                "M3",
                                [("TR-003", "1", "0"), ("TR-002", "0.05", "0")],
                                "900",
                                "550",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),
]

# Ítems que la versión BASE de Altos del Río NO incluye (se agregan en CONTROL) y viceversa.
ITEM_SOLO_CONTROL = "Impermeabilización de cubierta"
VALOR_MANUAL_SOLO_CONTROL = D("52000")
ITEM_SOLO_BASE = "Muro en ladrillo de arcilla perforación vertical"
# Ajustes de cantidad en CONTROL (factor sobre la cantidad BASE).
AJUSTES_CONTROL = {
    "Acero de refuerzo para estructura": D("1.06"),
    "Concreto 3000 psi para muros estructurales": D("1.03"),
    "Excavación mecánica en material común": D("0.90"),
    "Muro en bloque de concreto 12x20x40 cm": D("1.46"),  # absorbe el muro en ladrillo
    "Torre grúa (alquiler mensual)": D("1.2"),
}


@dataclass
class _Ctx:
    unidades: dict[str, Unidad] = field(default_factory=dict)
    ciudades: dict[str, Ciudad] = field(default_factory=dict)
    insumos: dict[str, Insumo] = field(default_factory=dict)
    items: dict[str, EdtNodo] = field(default_factory=dict)  # por descripción
    apus: dict[int, Apu] = field(default_factory=dict)  # por item_id
    cant_adr: dict[str, Decimal] = field(default_factory=dict)
    cant_mir: dict[str, Decimal] = field(default_factory=dict)
    creados: int = 0

    def add(self, db: Session, obj: object) -> None:
        db.add(obj)
        self.creados += 1


def _redondear_cientos(valor: Decimal) -> Decimal:
    return (valor / 100).quantize(D("1"), rounding=ROUND_HALF_UP) * 100


# ---------------------------------------------------------------------------------------
# Maestros
# ---------------------------------------------------------------------------------------
def _maestros(db: Session, ctx: _Ctx) -> None:
    for codigo, nombre in UNIDADES_EXTRA:
        if not db.scalar(select(Unidad).where(Unidad.codigo == codigo)):
            ctx.add(db, Unidad(codigo=codigo, nombre=nombre))
    db.flush()
    ctx.unidades = {u.codigo: u for u in db.scalars(select(Unidad))}
    ctx.ciudades = {c.codigo: c for c in db.scalars(select(Ciudad))}
    for req in ("BOG", "SOA"):
        if req not in ctx.ciudades:
            raise RuntimeError(f"Falta la ciudad {req}: ejecute primero seed_catalogos")

    for codigo, desc, unidad, tipo, _precio in INSUMOS:
        ins = db.scalar(select(Insumo).where(Insumo.codigo == codigo))
        if ins is None:
            ins = Insumo(codigo=codigo, descripcion=desc, unidad_id=ctx.unidades[unidad].id, tipo=tipo)
            ctx.add(db, ins)
        ctx.insumos[codigo] = ins
    db.flush()

    for ciudad_cod, factor_ciudad in (("BOG", D("1")), ("SOA", FACTOR_SOACHA)):
        ciudad = ctx.ciudades[ciudad_cod]
        for fecha, sufijo, julio in ((FECHA_LISTA_1, "2026-01", False), (FECHA_LISTA_2, "2026-07", True)):
            lista = ListaPrecios(
                codigo=f"LP-{ciudad_cod}-{sufijo}",
                nombre=f"Lista demo {ciudad.nombre} {sufijo}",
                ciudad_id=ciudad.id,
                fecha_desde=fecha,
                observaciones="Precios FICTICIOS para demostración",
            )
            ctx.add(db, lista)
            db.flush()
            for codigo, _d, _u, tipo, precio in INSUMOS:
                p = D(precio) * factor_ciudad
                if julio:
                    p *= 1 + INCREMENTO_JULIO_INSUMO.get(codigo, INCREMENTO_JULIO[tipo])
                ctx.add(
                    db,
                    PrecioInsumo(
                        lista_id=lista.id,
                        insumo_id=ctx.insumos[codigo].id,
                        precio=_redondear_cientos(p),
                        fuente="Cotización ficticia (demo)",
                    ),
                )
    db.flush()


def _proyectos(db: Session, ctx: _Ctx) -> tuple[Proyecto, Proyecto]:
    adr = Proyecto(
        codigo=PROYECTO_PRINCIPAL,
        nombre="Proyecto Demo Altos del Río",
        ciudad_id=ctx.ciudades["BOG"].id,
        tipo=TipoProyecto.VIS,
        estado=EstadoProyecto.EN_EJECUCION,
        fecha_inicio=date(2026, 8, 1),
        fecha_fin_estimada=date(2028, 6, 30),
        numero_unidades=240,
        descripcion="Proyecto FICTICIO de vivienda VIS para demostración (2 torres de 12 pisos).",
    )
    etapa = Etapa(codigo="E1", nombre="Etapa 1", orden=1, numero_unidades=240)
    etapa.torres = [
        Torre(codigo="T1", nombre="Torre 1", numero_pisos=12, numero_unidades=120),
        Torre(codigo="T2", nombre="Torre 2", numero_pisos=12, numero_unidades=120),
    ]
    adr.etapas = [etapa]
    mir = Proyecto(
        codigo="PD-MIR",
        nombre="Proyecto Demo Mirador",
        ciudad_id=ctx.ciudades["SOA"].id,
        tipo=TipoProyecto.NO_VIS,
        estado=EstadoProyecto.PLANEACION,
        fecha_inicio=date(2027, 2, 1),
        fecha_fin_estimada=date(2028, 12, 15),
        numero_unidades=120,
        descripcion="Proyecto FICTICIO No VIS para demostración (1 torre de 15 pisos).",
    )
    etapa_m = Etapa(codigo="E1", nombre="Etapa única", orden=1, numero_unidades=120)
    etapa_m.torres = [Torre(codigo="T1", nombre="Torre única", numero_pisos=15, numero_unidades=120)]
    mir.etapas = [etapa_m]
    db.add_all([adr, mir])
    ctx.creados += 2 + 2 + 3
    db.flush()
    return adr, mir


def _edt_y_apu(db: Session, ctx: _Ctx) -> None:
    for ci, (cap_desc, detalles) in enumerate(EDT, start=1):
        cap = EdtNodo(nivel=NivelEdt.CAPITULO, codigo=f"{ci:02d}", descripcion=cap_desc, orden=ci)
        ctx.add(db, cap)
        db.flush()
        for di, (det_desc, grupos) in enumerate(detalles, start=1):
            det = EdtNodo(
                nivel=NivelEdt.DETALLE,
                parent_id=cap.id,
                codigo=f"{cap.codigo}.{di:02d}",
                descripcion=det_desc,
                orden=di,
            )
            ctx.add(db, det)
            db.flush()
            for gi, (grp_desc, items) in enumerate(grupos, start=1):
                grp = EdtNodo(
                    nivel=NivelEdt.GRUPO,
                    parent_id=det.id,
                    codigo=f"{det.codigo}.{gi:03d}",
                    descripcion=grp_desc,
                    orden=gi,
                )
                ctx.add(db, grp)
                db.flush()
                for ii, (desc, unidad, comps, q_adr, q_mir) in enumerate(items, start=1):
                    item = EdtNodo(
                        nivel=NivelEdt.ITEM,
                        parent_id=grp.id,
                        codigo=f"{grp.codigo}.{ii:04d}",
                        descripcion=desc,
                        unidad_id=ctx.unidades[unidad].id,
                        orden=ii,
                    )
                    ctx.add(db, item)
                    db.flush()
                    apu = Apu(item_id=item.id, descripcion=f"APU {desc}")
                    apu.insumos = [
                        ApuInsumo(
                            insumo_id=ctx.insumos[cod].id, cantidad=D(cant), desperdicio_pct=D(desp), orden=k
                        )
                        for k, (cod, cant, desp) in enumerate(comps, start=1)
                    ]
                    ctx.add(db, apu)
                    ctx.creados += len(comps)
                    ctx.items[desc] = item
                    ctx.cant_adr[desc] = D(q_adr)
                    ctx.cant_mir[desc] = D(q_mir)
    db.flush()
    ctx.apus = {a.item_id: a for a in db.scalars(select(Apu))}


# ---------------------------------------------------------------------------------------
# Presupuestos
# ---------------------------------------------------------------------------------------
def _linea_apu(
    db: Session, ctx: _Ctx, version: PresupuestoVersion, item: EdtNodo, cantidad: Decimal, orden: int
) -> PresupuestoLinea:
    val = valorizar_apu(db, ctx.apus[item.id], version.ciudad_precios_id, version.fecha_precios)
    linea = PresupuestoLinea(
        version_id=version.id,
        item_id=item.id,
        cantidad=cantidad,
        valor_unitario=val.valor_unitario,
        valor_total=valor_total_linea(cantidad, val.valor_unitario),
        origen_unitario=OrigenValor.APU,
        orden=orden,
    )
    linea.insumos = [
        PresupuestoLineaInsumo(
            insumo_id=c.insumo_id,
            cantidad_unitaria=c.cantidad,
            desperdicio_pct=c.desperdicio_pct,
            precio_unitario=c.precio_unitario,
            valor_unitario=c.valor_unitario,
            precio_faltante=c.precio_faltante,
        )
        for c in val.componentes
    ]
    ctx.add(db, linea)
    ctx.creados += len(linea.insumos)
    return linea


def _aprobar(db: Session, version: PresupuestoVersion) -> None:
    db.flush()
    cd = sum((ln.valor_total for ln in version.lineas), D("0"))
    aiu = calcular_aiu(
        cd,
        version.administracion_pct,
        version.imprevistos_pct,
        version.utilidad_pct,
        version.iva_utilidad_pct,
    )
    version.estado = EstadoVersion.APROBADO
    version.total_costo_directo = aiu.costo_directo
    version.total_presupuesto = aiu.total
    version.aprobado_at = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)
    version.aprobado_por = USUARIO_SEED
    registrar_auditoria(
        db,
        accion=Accion.APROBAR,
        entidad="presupuesto_version",
        entidad_id=version.id,
        detalle={
            "total_costo_directo": aiu.costo_directo,
            "total_presupuesto": aiu.total,
            "origen": "seed demo",
        },
    )


def _presupuestos(
    db: Session, ctx: _Ctx, adr: Proyecto, mir: Proyecto
) -> tuple[Presupuesto, PresupuestoVersion]:
    bog, soa = ctx.ciudades["BOG"], ctx.ciudades["SOA"]
    pre_adr = Presupuesto(
        proyecto_id=adr.id,
        etapa_id=adr.etapas[0].id,
        codigo="PRE-ADR-E1",
        nombre="Presupuesto Altos del Río - Etapa 1",
        descripcion="Presupuesto de demostración (datos ficticios)",
    )
    ctx.add(db, pre_adr)
    db.flush()

    # v1 BASE aprobada (precios de enero)
    base = PresupuestoVersion(
        presupuesto_id=pre_adr.id,
        numero=1,
        tipo=TipoVersion.BASE,
        estado=EstadoVersion.BORRADOR,
        nombre="Presupuesto base",
        descripcion="Base aprobada con precios vigentes a marzo de 2026",
        fecha_precios=FECHA_PRECIOS_BASE,
        ciudad_precios_id=bog.id,
        **AIU_DEMO,
    )
    ctx.add(db, base)
    db.flush()
    orden = 0
    for desc, item in ctx.items.items():
        if desc == ITEM_SOLO_CONTROL:
            continue
        orden += 1
        base.lineas.append(_linea_apu(db, ctx, base, item, ctx.cant_adr[desc], orden))
    _aprobar(db, base)

    # v2 CONTROL en borrador (copia de la base, precios de julio y cambios de cantidades)
    control = PresupuestoVersion(
        presupuesto_id=pre_adr.id,
        numero=2,
        tipo=TipoVersion.CONTROL,
        estado=EstadoVersion.BORRADOR,
        nombre="Presupuesto de control (ajuste agosto 2026)",
        descripcion="Copia de la base revalorizada a agosto de 2026 con ajustes de cantidades de obra",
        fecha_precios=FECHA_PRECIOS_CONTROL,
        ciudad_precios_id=bog.id,
        version_origen_id=base.id,
        **AIU_DEMO,
    )
    ctx.add(db, control)
    db.flush()
    orden = 0
    for desc, item in ctx.items.items():
        orden += 1
        if desc == ITEM_SOLO_BASE:
            continue
        if desc == ITEM_SOLO_CONTROL:
            cant = ctx.cant_adr[desc]
            linea = PresupuestoLinea(
                version_id=control.id,
                item_id=item.id,
                cantidad=cant,
                valor_unitario=VALOR_MANUAL_SOLO_CONTROL,
                valor_total=valor_total_linea(cant, VALOR_MANUAL_SOLO_CONTROL),
                origen_unitario=OrigenValor.MANUAL,
                orden=orden,
                observacion="Valor de cotización ficticia (sin APU desglosado)",
            )
            ctx.add(db, linea)
            continue
        cant = ctx.cant_adr[desc] * AJUSTES_CONTROL.get(desc, D("1"))
        _linea_apu(db, ctx, control, item, cant.quantize(D("0.0001")), orden)
    registrar_auditoria(
        db,
        accion=Accion.COPIAR,
        entidad="presupuesto_version",
        entidad_id=control.id,
        detalle={"version_origen_id": base.id, "recalcular_precios": True, "origen": "seed demo"},
    )

    # Mirador: v1 BASE en borrador (precios de Soacha, julio)
    pre_mir = Presupuesto(
        proyecto_id=mir.id,
        etapa_id=mir.etapas[0].id,
        codigo="PRE-MIR-E1",
        nombre="Presupuesto Mirador - Etapa única",
        descripcion="Presupuesto de demostración (datos ficticios)",
    )
    ctx.add(db, pre_mir)
    db.flush()
    base_m = PresupuestoVersion(
        presupuesto_id=pre_mir.id,
        numero=1,
        tipo=TipoVersion.BASE,
        estado=EstadoVersion.BORRADOR,
        nombre="Presupuesto base (en elaboración)",
        fecha_precios=FECHA_PRECIOS_CONTROL,
        ciudad_precios_id=soa.id,
        administracion_pct=D("0.08"),
        imprevistos_pct=D("0.02"),
        utilidad_pct=D("0.06"),
        iva_utilidad_pct=D("0.19"),
    )
    ctx.add(db, base_m)
    db.flush()
    for orden, (desc, item) in enumerate(ctx.items.items(), start=1):
        _linea_apu(db, ctx, base_m, item, ctx.cant_mir[desc], orden)
    db.flush()
    return pre_adr, base


# ---------------------------------------------------------------------------------------
# Control: compromisos y ejecución
# ---------------------------------------------------------------------------------------
# (tipo, número, fecha, tercero FICTICIO, descripción, estado, [(ítem, insumo|None, cantidad, valor unitario)])
COMPROMISOS = [
    (
        TipoCompromiso.CONTRATO,
        "CT-0001",
        date(2026, 8, 3),
        "Excavaciones Ejemplo S.A.S.",
        "Movimiento de tierras etapa 1",
        EstadoCompromiso.VIGENTE,
        [
            ("Excavación mecánica en material común", None, "2400", "36500"),
            ("Relleno compactado con recebo", None, "650", "142000"),
            ("Retiro de sobrantes en volqueta", None, "1800", "47000"),
        ],
    ),
    (
        TipoCompromiso.CONTRATO,
        "CT-0002",
        date(2026, 8, 10),
        "Pilotajes Demo del Centro S.A.S.",
        "Pilotaje preexcavado D=0.40 m",
        EstadoCompromiso.VIGENTE,
        [("Pilote preexcavado D=0.40 m", "SUB-001", "1800", "182000")],
    ),
    (
        TipoCompromiso.ORDEN_COMPRA,
        "OC-0001",
        date(2026, 8, 20),
        "Concretos Ficticios S.A.S.",
        "Suministro de concreto premezclado",
        EstadoCompromiso.VIGENTE,
        [
            ("Concreto 4000 psi para dados y vigas de cimentación", "MAT-002", "430", "590000"),
            ("Concreto 3000 psi para muros estructurales", "MAT-001", "900", "548000"),
        ],
    ),
    (
        TipoCompromiso.ORDEN_COMPRA,
        "OC-0002",
        date(2026, 9, 1),
        "Aceros Demo Andinos S.A.S.",
        "Suministro de acero figurado",
        EstadoCompromiso.VIGENTE,
        [
            ("Acero de refuerzo para cimentación", "MAT-004", "54600", "4950"),
            ("Acero de refuerzo para estructura", "MAT-004", "60000", "4950"),
        ],
    ),
    (
        TipoCompromiso.ORDEN_SERVICIO,
        "OS-0001",
        date(2026, 8, 1),
        "Topografía Ejemplo Ltda.",
        "Localización y replanteo",
        EstadoCompromiso.LIQUIDADO,
        [("Localización y replanteo con equipo de precisión", None, "4200", "2300")],
    ),
    (
        TipoCompromiso.ORDEN_COMPRA,
        "OC-0003",
        date(2026, 9, 15),
        "Proveedor Demo S.A.S.",
        "Orden duplicada por error (anulada)",
        EstadoCompromiso.ANULADO,
        [("Malla electrosoldada para losas", "MAT-005", "5000", "19500")],
    ),
]

PERIODOS = ["2026-08", "2026-09", "2026-10"]
# Avance físico ACUMULADO por periodo + factor de valor ejecutado vs presupuestado + compromiso.
EJECUCION = [
    ("Localización y replanteo con equipo de precisión", ["0.70", "1", "1"], "0.95", "OS-0001"),
    ("Descapote y limpieza manual e=0.20 m", ["1", "1", "1"], "1", None),
    ("Cerramiento provisional en lámina de zinc h=2.10 m", ["1", "1", "1"], "1.02", None),
    ("Retiro de sobrantes en volqueta", ["0.40", "0.85", "1"], "1.05", "CT-0001"),
    ("Excavación mecánica en material común", ["0.45", "0.90", "1"], "1.04", "CT-0001"),
    ("Relleno compactado con recebo", ["0", "0.40", "0.75"], "1", "CT-0001"),
    ("Pilote preexcavado D=0.40 m", ["0.30", "0.80", "1"], "0.98", "CT-0002"),
    ("Solado en concreto pobre e=0.05 m", ["0", "0.60", "1"], "1", None),
    ("Concreto 4000 psi para dados y vigas de cimentación", ["0", "0.35", "0.80"], "1.03", "OC-0001"),
    ("Acero de refuerzo para cimentación", ["0", "0.45", "0.85"], "1.06", "OC-0002"),
    ("Concreto 3000 psi para muros estructurales", ["0", "0", "0.08"], "1.05", "OC-0001"),
    ("Acero de refuerzo para estructura", ["0", "0", "0.10"], "1.07", "OC-0002"),
    ("Torre grúa (alquiler mensual)", ["0", "0.10", "0.20"], "1", None),
]


def _control(db: Session, ctx: _Ctx, pre: Presupuesto, base: PresupuestoVersion) -> None:
    compromisos: dict[str, Compromiso] = {}
    for tipo, numero, fecha, tercero, desc, estado, lineas in COMPROMISOS:
        comp = Compromiso(
            presupuesto_id=pre.id,
            tipo=tipo,
            numero=numero,
            fecha=fecha,
            tercero=tercero,
            descripcion=desc,
            estado=estado,
        )
        total = D("0")
        for item_desc, insumo_cod, cant, vu in lineas:
            vt = valor_total_linea(D(cant), D(vu))
            total += vt
            comp.lineas.append(
                CompromisoLinea(
                    item_id=ctx.items[item_desc].id,
                    insumo_id=ctx.insumos[insumo_cod].id if insumo_cod else None,
                    descripcion=item_desc,
                    cantidad=D(cant),
                    valor_unitario=D(vu),
                    valor_total=vt,
                )
            )
        comp.valor_total = total
        ctx.add(db, comp)
        ctx.creados += len(lineas)
        compromisos[numero] = comp
        if estado is EstadoCompromiso.ANULADO:
            db.flush()
            registrar_auditoria(
                db,
                accion=Accion.ANULAR,
                entidad="compromiso",
                entidad_id=comp.id,
                detalle={"motivo": "Orden duplicada (demo)", "origen": "seed demo"},
            )
    db.flush()

    totales_base = {ln.item_id: (ln.cantidad, ln.valor_total) for ln in base.lineas}
    for item_desc, avances, factor, comp_num in EJECUCION:
        item = ctx.items[item_desc]
        cant_base, valor_base = totales_base[item.id]
        previo = D("0")
        for periodo, av in zip(PERIODOS, avances, strict=True):
            avance = D(av)
            delta = avance - previo
            if delta == 0:  # sin avance en el periodo: no se registra
                continue
            ctx.add(
                db,
                Ejecucion(
                    presupuesto_id=pre.id,
                    item_id=item.id,
                    periodo=periodo,
                    valor_ejecutado=redondear_pesos(valor_base * delta * D(factor)),
                    cantidad_ejecutada=(cant_base * delta).quantize(D("0.0001")),
                    avance_fisico_pct=avance,
                    compromiso_id=compromisos[comp_num].id if comp_num else None,
                    observacion="Avance de demostración (ficticio)",
                ),
            )
            previo = avance
    db.flush()


def run(db: Session) -> int:
    """Carga los datos demo. Retorna el número de registros creados (0 si ya existían)."""
    if db.scalar(select(Proyecto.id).where(Proyecto.codigo == PROYECTO_PRINCIPAL)) is not None:
        return 0
    ctx = _Ctx()
    _maestros(db, ctx)
    adr, mir = _proyectos(db, ctx)
    _edt_y_apu(db, ctx)
    pre_adr, base = _presupuestos(db, ctx, adr, mir)
    _control(db, ctx, pre_adr, base)
    registrar_auditoria(
        db,
        accion=Accion.IMPORTAR,
        entidad="seed_demo",
        detalle={"registros": ctx.creados},
    )
    db.commit()
    return ctx.creados
