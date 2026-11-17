"""Modelos SQLAlchemy del módulo ADPRO (presupuesto y control de obra).

PROPIEDAD: agente ARQUITECTO. Los agentes de submódulos NO modifican este archivo; piden
cambios vía ``model_change_requests``. Cualquier cambio requiere migración Alembic nueva.

Mapa de tablas (prefijo ``adpro_``):

    Maestros     ciudad, unidad, insumo, lista_precios, precio_insumo,
                 proyecto, etapa, torre, edt_nodo
    APU          apu, apu_insumo
    Presupuesto  presupuesto, presupuesto_version, presupuesto_linea, presupuesto_linea_insumo
    Control      compromiso, compromiso_linea, ejecucion

Decisiones clave (ver docs/ARQUITECTURA.md):
- EDT en UNA tabla jerárquica (``adpro_edt_nodo``) con ``nivel`` y ``parent_id``.
- Un APU por ítem EDT (v1). Sin sub-APU (mejora futura).
- Precio vigente = precio del insumo en la lista de la ciudad con mayor ``fecha_desde`` <= fecha.
- Cada línea de presupuesto guarda el SNAPSHOT de su composición (``presupuesto_linea_insumo``)
  y su valor unitario; al aprobar la versión queda congelado (inmutable).
- Porcentajes como FRACCIÓN (0.05 = 5 %). Dinero/cantidades Numeric(18,4); coeficientes
  APU Numeric(18,6).
- AIU vive en la propia versión (cada versión congela su configuración).
- Búsqueda por texto (filtros ``q``): en PostgreSQL la migración 0002 crea índices GIN
  ``pg_trgm`` sobre ``lower(codigo)`` y ``lower(descripcion)`` de insumo y edt_nodo. No se
  declaran aquí por ser específicos del motor (``alembic/env.py`` los excluye de autogenerate).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Coef, Money, Pct, Qty, TimestampMixin, UTCDateTime, str_enum
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

ZERO = Decimal("0")

# =====================================================================================
# MAESTROS
# =====================================================================================


class Ciudad(TimestampMixin, Base):
    """Ciudad / regional. Determina la lista de precios aplicable."""

    __tablename__ = "adpro_ciudad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # p. ej. BOG
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    departamento: Mapped[str | None] = mapped_column(String(100))
    regional: Mapped[str | None] = mapped_column(String(100))  # agrupador comercial/operativo
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Unidad(TimestampMixin, Base):
    """Unidad de medida (M2, M3, UN, KG, GL, ML, DIA, HR...)."""

    __tablename__ = "adpro_unidad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Insumo(TimestampMixin, Base):
    __tablename__ = "adpro_insumo"
    __table_args__ = (Index("ix_adpro_insumo_tipo_activo", "tipo", "activo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("adpro_unidad.id", ondelete="RESTRICT"), nullable=False)
    tipo: Mapped[TipoInsumo] = mapped_column(str_enum(TipoInsumo), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    observaciones: Mapped[str | None] = mapped_column(Text)

    unidad: Mapped[Unidad] = relationship(lazy="joined")


class ListaPrecios(TimestampMixin, Base):
    """Lista de precios de insumos para una ciudad, vigente DESDE ``fecha_desde``.

    Histórico: nunca se sobreescribe una lista antigua; se crea una nueva con fecha posterior.
    """

    __tablename__ = "adpro_lista_precios"
    __table_args__ = (UniqueConstraint("ciudad_id", "fecha_desde"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    ciudad_id: Mapped[int] = mapped_column(ForeignKey("adpro_ciudad.id", ondelete="RESTRICT"), nullable=False)
    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    observaciones: Mapped[str | None] = mapped_column(Text)

    ciudad: Mapped[Ciudad] = relationship(lazy="joined")
    precios: Mapped[list[PrecioInsumo]] = relationship(
        back_populates="lista", cascade="all, delete-orphan", passive_deletes=True
    )


class PrecioInsumo(TimestampMixin, Base):
    __tablename__ = "adpro_precio_insumo"
    __table_args__ = (
        UniqueConstraint("lista_id", "insumo_id"),
        CheckConstraint("precio >= 0", name="precio_no_negativo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lista_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_lista_precios.id", ondelete="CASCADE"), nullable=False
    )
    insumo_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_insumo.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    precio: Mapped[Decimal] = mapped_column(Money, nullable=False)
    fuente: Mapped[str | None] = mapped_column(String(200))  # cotización, proveedor ficticio, etc.

    lista: Mapped[ListaPrecios] = relationship(back_populates="precios")
    insumo: Mapped[Insumo] = relationship()


class Proyecto(TimestampMixin, Base):
    __tablename__ = "adpro_proyecto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    ciudad_id: Mapped[int] = mapped_column(ForeignKey("adpro_ciudad.id", ondelete="RESTRICT"), nullable=False)
    tipo: Mapped[TipoProyecto] = mapped_column(str_enum(TipoProyecto), nullable=False)
    estado: Mapped[EstadoProyecto] = mapped_column(
        str_enum(EstadoProyecto), nullable=False, default=EstadoProyecto.PLANEACION
    )
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin_estimada: Mapped[date | None] = mapped_column(Date)
    numero_unidades: Mapped[int | None] = mapped_column(Integer)  # viviendas totales
    descripcion: Mapped[str | None] = mapped_column(Text)

    ciudad: Mapped[Ciudad] = relationship(lazy="joined")
    etapas: Mapped[list[Etapa]] = relationship(
        back_populates="proyecto", cascade="all, delete-orphan", order_by="Etapa.orden"
    )


class Etapa(TimestampMixin, Base):
    __tablename__ = "adpro_etapa"
    __table_args__ = (UniqueConstraint("proyecto_id", "codigo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_proyecto.id", ondelete="CASCADE"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    numero_unidades: Mapped[int | None] = mapped_column(Integer)

    proyecto: Mapped[Proyecto] = relationship(back_populates="etapas")
    torres: Mapped[list[Torre]] = relationship(
        back_populates="etapa", cascade="all, delete-orphan", order_by="Torre.codigo"
    )


class Torre(TimestampMixin, Base):
    __tablename__ = "adpro_torre"
    __table_args__ = (UniqueConstraint("etapa_id", "codigo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    etapa_id: Mapped[int] = mapped_column(ForeignKey("adpro_etapa.id", ondelete="CASCADE"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    numero_pisos: Mapped[int | None] = mapped_column(Integer)
    numero_unidades: Mapped[int | None] = mapped_column(Integer)

    etapa: Mapped[Etapa] = relationship(back_populates="torres")


class EdtNodo(TimestampMixin, Base):
    """Nodo de la EDT presupuestal (catálogo corporativo estilo ProdesaClass).

    Jerarquía estricta: CAPITULO (raíz) -> DETALLE -> GRUPO -> ITEM.
    ``codigo`` es el código jerárquico completo y único (recomendado: ``CC``, ``CC.DD``,
    ``CC.DD.GGG``, ``CC.DD.GGG.IIII``). Solo los ITEM tienen unidad y pueden tener APU y
    líneas de presupuesto. Las reglas de jerarquía se validan en ``maestros/service.py``.
    """

    __tablename__ = "adpro_edt_nodo"
    __table_args__ = (
        Index("ix_adpro_edt_nodo_parent_orden", "parent_id", "orden"),
        CheckConstraint("(nivel <> 'ITEM') OR (unidad_id IS NOT NULL)", name="item_requiere_unidad"),
        CheckConstraint("(nivel = 'CAPITULO') OR (parent_id IS NOT NULL)", name="requiere_padre"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("adpro_edt_nodo.id", ondelete="RESTRICT"))
    nivel: Mapped[NivelEdt] = mapped_column(str_enum(NivelEdt), nullable=False, index=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("adpro_unidad.id", ondelete="RESTRICT"))
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notas: Mapped[str | None] = mapped_column(Text)  # "notas clave" del ítem

    parent: Mapped[EdtNodo | None] = relationship(remote_side=[id], back_populates="hijos")
    hijos: Mapped[list[EdtNodo]] = relationship(back_populates="parent", order_by="EdtNodo.orden")
    unidad: Mapped[Unidad | None] = relationship(lazy="joined")


# =====================================================================================
# APU
# =====================================================================================


class Apu(TimestampMixin, Base):
    """Análisis de Precio Unitario de un ítem EDT (uno por ítem en v1).

    valor_unitario(fecha, ciudad) = Σ cantidad · (1 + desperdicio_pct) · precio_vigente(insumo)
    El valor NO se persiste aquí (depende de fecha/ciudad); se congela en las líneas de presupuesto.
    """

    __tablename__ = "adpro_apu"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_edt_nodo.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    descripcion: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    observaciones: Mapped[str | None] = mapped_column(Text)

    item: Mapped[EdtNodo] = relationship()
    insumos: Mapped[list[ApuInsumo]] = relationship(
        back_populates="apu", cascade="all, delete-orphan", order_by="ApuInsumo.orden"
    )


class ApuInsumo(TimestampMixin, Base):
    __tablename__ = "adpro_apu_insumo"
    __table_args__ = (
        UniqueConstraint("apu_id", "insumo_id"),
        CheckConstraint("cantidad >= 0", name="cantidad_no_negativa"),
        CheckConstraint("desperdicio_pct >= 0", name="desperdicio_no_negativo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    apu_id: Mapped[int] = mapped_column(ForeignKey("adpro_apu.id", ondelete="CASCADE"), nullable=False)
    insumo_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_insumo.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cantidad: Mapped[Decimal] = mapped_column(Coef, nullable=False)  # por unidad del ítem
    desperdicio_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, default=ZERO)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observacion: Mapped[str | None] = mapped_column(String(300))

    apu: Mapped[Apu] = relationship(back_populates="insumos")
    insumo: Mapped[Insumo] = relationship(lazy="joined")


# =====================================================================================
# PRESUPUESTO
# =====================================================================================


class Presupuesto(TimestampMixin, Base):
    """Presupuesto de un proyecto (opcionalmente de una etapa). Contiene versiones."""

    __tablename__ = "adpro_presupuesto"
    __table_args__ = (UniqueConstraint("proyecto_id", "codigo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_proyecto.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    etapa_id: Mapped[int | None] = mapped_column(ForeignKey("adpro_etapa.id", ondelete="RESTRICT"))
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)

    proyecto: Mapped[Proyecto] = relationship()
    etapa: Mapped[Etapa | None] = relationship()
    versiones: Mapped[list[PresupuestoVersion]] = relationship(
        back_populates="presupuesto",
        cascade="all, delete-orphan",
        order_by="PresupuestoVersion.numero",
        foreign_keys="PresupuestoVersion.presupuesto_id",
    )


class PresupuestoVersion(TimestampMixin, Base):
    """Versión de un presupuesto. BORRADOR -> APROBADO -> CERRADO.

    Aprobada o cerrada = INMUTABLE (líneas, snapshot de insumos y AIU). Los totales se
    congelan en ``total_costo_directo`` / ``total_presupuesto`` al aprobar.
    """

    __tablename__ = "adpro_presupuesto_version"
    __table_args__ = (
        UniqueConstraint("presupuesto_id", "numero"),
        Index("ix_adpro_presupuesto_version_tipo_estado", "presupuesto_id", "tipo", "estado"),
        CheckConstraint(
            "administracion_pct >= 0 AND imprevistos_pct >= 0 AND utilidad_pct >= 0 AND iva_utilidad_pct >= 0",
            name="aiu_no_negativo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    presupuesto_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_presupuesto.id", ondelete="CASCADE"), nullable=False
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)  # consecutivo por presupuesto
    tipo: Mapped[TipoVersion] = mapped_column(str_enum(TipoVersion), nullable=False)
    estado: Mapped[EstadoVersion] = mapped_column(
        str_enum(EstadoVersion), nullable=False, default=EstadoVersion.BORRADOR
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)

    # Parámetros de valorización (precios vigentes a esta fecha en esta ciudad)
    fecha_precios: Mapped[date] = mapped_column(Date, nullable=False)
    ciudad_precios_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_ciudad.id", ondelete="RESTRICT"), nullable=False
    )

    # AIU + IVA sobre utilidad (fracciones)
    administracion_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, default=ZERO)
    imprevistos_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, default=ZERO)
    utilidad_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, default=ZERO)
    iva_utilidad_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, default=Decimal("0.19"))

    version_origen_id: Mapped[int | None] = mapped_column(
        ForeignKey("adpro_presupuesto_version.id", ondelete="SET NULL")
    )
    aprobado_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    aprobado_por: Mapped[str | None] = mapped_column(String(150))
    cerrado_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cerrado_por: Mapped[str | None] = mapped_column(String(150))

    # Snapshot de totales al aprobar (null mientras sea BORRADOR)
    total_costo_directo: Mapped[Decimal | None] = mapped_column(Money)
    total_presupuesto: Mapped[Decimal | None] = mapped_column(Money)

    presupuesto: Mapped[Presupuesto] = relationship(back_populates="versiones", foreign_keys=[presupuesto_id])
    ciudad_precios: Mapped[Ciudad] = relationship()
    version_origen: Mapped[PresupuestoVersion | None] = relationship(remote_side=[id])
    lineas: Mapped[list[PresupuestoLinea]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="PresupuestoLinea.orden"
    )


class PresupuestoLinea(TimestampMixin, Base):
    """Línea de presupuesto: un ítem EDT con cantidad y valor unitario.

    valor_total = redondeo_pesos(cantidad * valor_unitario).
    """

    __tablename__ = "adpro_presupuesto_linea"
    __table_args__ = (
        UniqueConstraint("version_id", "item_id"),
        CheckConstraint("cantidad >= 0", name="cantidad_no_negativa"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_presupuesto_version.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_edt_nodo.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cantidad: Mapped[Decimal] = mapped_column(Qty, nullable=False, default=ZERO)
    valor_unitario: Mapped[Decimal] = mapped_column(Money, nullable=False, default=ZERO)
    valor_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=ZERO)
    origen_unitario: Mapped[OrigenValor] = mapped_column(
        str_enum(OrigenValor), nullable=False, default=OrigenValor.APU
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observacion: Mapped[str | None] = mapped_column(String(500))

    version: Mapped[PresupuestoVersion] = relationship(back_populates="lineas")
    item: Mapped[EdtNodo] = relationship(lazy="joined")
    insumos: Mapped[list[PresupuestoLineaInsumo]] = relationship(
        back_populates="linea", cascade="all, delete-orphan"
    )


class PresupuestoLineaInsumo(Base):
    """Snapshot de la composición APU de una línea (base de la explosión de insumos).

    valor_unitario = cantidad_unitaria * (1 + desperdicio_pct) * precio_unitario  (por unidad de ítem)
    Cantidad total del insumo en la línea = linea.cantidad * cantidad_unitaria * (1 + desperdicio_pct)
    Las líneas MANUAL/IMPORTADO sin APU no tienen filas aquí.
    """

    __tablename__ = "adpro_presupuesto_linea_insumo"
    __table_args__ = (UniqueConstraint("linea_id", "insumo_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    linea_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_presupuesto_linea.id", ondelete="CASCADE"), nullable=False
    )
    insumo_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_insumo.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cantidad_unitaria: Mapped[Decimal] = mapped_column(Coef, nullable=False)
    desperdicio_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, default=ZERO)
    precio_unitario: Mapped[Decimal] = mapped_column(Money, nullable=False, default=ZERO)
    valor_unitario: Mapped[Decimal] = mapped_column(Money, nullable=False, default=ZERO)
    precio_faltante: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    linea: Mapped[PresupuestoLinea] = relationship(back_populates="insumos")
    insumo: Mapped[Insumo] = relationship(lazy="joined")


# =====================================================================================
# CONTROL
# =====================================================================================


class Compromiso(TimestampMixin, Base):
    """Orden de compra / contrato (registro simplificado) contra ítems de un presupuesto.

    Se asocia al PRESUPUESTO (no a una versión) para sobrevivir a nuevas versiones de control;
    el tablero cruza por ``item_id`` contra la versión de control elegida.
    """

    __tablename__ = "adpro_compromiso"
    __table_args__ = (
        UniqueConstraint("presupuesto_id", "tipo", "numero"),
        Index("ix_adpro_compromiso_presupuesto_estado", "presupuesto_id", "estado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    presupuesto_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_presupuesto.id", ondelete="RESTRICT"), nullable=False
    )
    tipo: Mapped[TipoCompromiso] = mapped_column(str_enum(TipoCompromiso), nullable=False)
    numero: Mapped[str] = mapped_column(String(30), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tercero: Mapped[str] = mapped_column(String(200), nullable=False)  # SOLO nombres ficticios
    descripcion: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[EstadoCompromiso] = mapped_column(
        str_enum(EstadoCompromiso), nullable=False, default=EstadoCompromiso.VIGENTE
    )
    valor_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=ZERO)  # Σ líneas

    presupuesto: Mapped[Presupuesto] = relationship()
    lineas: Mapped[list[CompromisoLinea]] = relationship(
        back_populates="compromiso", cascade="all, delete-orphan"
    )


class CompromisoLinea(TimestampMixin, Base):
    __tablename__ = "adpro_compromiso_linea"
    __table_args__ = (CheckConstraint("cantidad >= 0", name="cantidad_no_negativa"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    compromiso_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_compromiso.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_edt_nodo.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    insumo_id: Mapped[int | None] = mapped_column(ForeignKey("adpro_insumo.id", ondelete="RESTRICT"))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    cantidad: Mapped[Decimal] = mapped_column(Qty, nullable=False, default=ZERO)
    valor_unitario: Mapped[Decimal] = mapped_column(Money, nullable=False, default=ZERO)
    valor_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=ZERO)

    compromiso: Mapped[Compromiso] = relationship(back_populates="lineas")
    item: Mapped[EdtNodo] = relationship(lazy="joined")
    insumo: Mapped[Insumo | None] = relationship()


class Ejecucion(TimestampMixin, Base):
    """Ejecución/avance de un ítem en un periodo mensual.

    - ``periodo``: 'YYYY-MM'.
    - ``valor_ejecutado`` y ``cantidad_ejecutada``: lo ejecutado EN el periodo (no acumulado).
    - ``avance_fisico_pct``: avance físico ACUMULADO al cierre del periodo (fracción 0..1).
    """

    __tablename__ = "adpro_ejecucion"
    __table_args__ = (
        UniqueConstraint("presupuesto_id", "item_id", "periodo"),
        Index("ix_adpro_ejecucion_presupuesto_periodo", "presupuesto_id", "periodo"),
        CheckConstraint("avance_fisico_pct >= 0 AND avance_fisico_pct <= 1", name="avance_entre_0_y_1"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    presupuesto_id: Mapped[int] = mapped_column(
        ForeignKey("adpro_presupuesto.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("adpro_edt_nodo.id", ondelete="RESTRICT"), nullable=False)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    valor_ejecutado: Mapped[Decimal] = mapped_column(Money, nullable=False, default=ZERO)
    cantidad_ejecutada: Mapped[Decimal | None] = mapped_column(Qty)
    avance_fisico_pct: Mapped[Decimal] = mapped_column(Pct, nullable=False, default=ZERO)
    compromiso_id: Mapped[int | None] = mapped_column(ForeignKey("adpro_compromiso.id", ondelete="SET NULL"))
    observacion: Mapped[str | None] = mapped_column(String(500))

    item: Mapped[EdtNodo] = relationship(lazy="joined")
    compromiso: Mapped[Compromiso | None] = relationship()
