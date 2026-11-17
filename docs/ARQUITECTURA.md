# Arquitectura — ERP Prodesa

> Prototipo local → presentación a directivos → piloto → producción.
> Módulo 1: **ADPRO** (presupuesto y control de obra). Inspirado funcionalmente en ERPs de
> construcción del mercado, diseñado desde los procesos de Prodesa (EDT ProdesaClass, versiones
> BASE/FIC/FIV/CONTROL, comparativos). No reutiliza código, pantallas ni textos de terceros.

## 1. Decisiones principales (ADR resumidos)

| # | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|
| 1 | **Monolito modular** (un backend, módulos aislados por carpeta) | Equipo pequeño, un solo despliegue, transacciones ACID entre presupuesto y control; se puede partir en servicios después si un módulo lo justifica | Microservicios desde el día 1 (costo operativo alto, consistencia distribuida) |
| 2 | **Python 3.12 + FastAPI + SQLAlchemy 2 + Pydantic v2** | Productividad, tipado, OpenAPI automático, ecosistema de datos (Excel, pandas) que ya usa el área | Django (más acoplado), .NET (menos afín al equipo actual) |
| 3 | **PostgreSQL** en producción, **SQLite** en el prototipo | SQLite = cero instalación para la demo; el código es agnóstico (sin tipos nativos, `str_enum` VARCHAR+CHECK, `Numeric`) | Solo PostgreSQL (fricción para la demo local) |
| 4 | **Alembic** para el esquema | Migraciones versionadas y reproducibles; `render_as_batch` en SQLite | `create_all` en producción |
| 5 | **Decimal** extremo a extremo; JSON con decimales como string | Dinero exacto; ROUND_HALF_UP a pesos al final | `float` (errores de redondeo inaceptables) |
| 6 | **Versiones inmutables** de presupuesto con snapshot de precios | Trazabilidad y auditoría: lo aprobado nunca cambia aunque cambien APU o listas de precios | Recalcular siempre en vivo |
| 7 | **EDT en una tabla jerárquica** (`adpro_edt_nodo`: `nivel` + `parent_id`) | Una sola consulta de árbol, código jerárquico único, fácil de importar desde ProdesaClass; reglas de nivel validadas en service + CHECK | 4 tablas (capítulo/detalle/grupo/ítem): más joins y endpoints duplicados |
| 8 | **Auth local JWT** en el prototipo, **Microsoft Entra ID** en producción | Demo autónoma; el resto del código solo depende de `get_current_user`/`require_role` | Entra ID desde el prototipo (requiere registro de app y TI) |
| 9 | **React 18 + Vite + TypeScript + TanStack Query** | SPA rápida, tipada; el contrato OpenAPI permite generar tipos | Server-side templates |
| 10 | **Auditoría doble**: columnas `created/updated_at/by` en toda entidad + `core_audit_log` para eventos de negocio | Quién cambió qué y cuándo, requerido para aprobación por directivos | Solo logs de aplicación |

## 2. Capas y estructura

```
backend/
  app/
    main.py                  # create_app(): CORS, errores, routers
    db_models.py             # importa TODOS los modelos (Alembic/tests)
    seed.py                  # usuarios de prueba + catálogos básicos
    core/                    # transversal (no depende de ningún módulo)
      config.py  db.py  security.py  audit.py  errors.py  schemas.py  models.py  auth_router.py
    modules/
      adpro/
        models.py  enums.py  calculos.py  valorizacion.py  router.py   # fundación (arquitecto)
        maestros/    router.py schemas.py service.py
        apu/         router.py schemas.py service.py
        presupuesto/ router.py schemas.py service.py
        control/     router.py schemas.py service.py
      # futuros: compras/, contratos/, comercial/, tesoreria/, contabilidad/
  alembic/versions/          # migraciones
  tests/                     # espejo de app/: tests/adpro/<submodulo>/test_*.py
frontend/                    # SPA React (agente de frontend)
docs/                        # este documento + API_CONTRATO.md
```

**Flujo de una petición**: `router.py` (HTTP, validación Pydantic, roles) → `service.py` (reglas
de negocio, transacción, auditoría) → `models.py` (SQLAlchemy) → BD.

Reglas de dependencia:
- `core` no importa `modules`.
- Un submódulo solo usa de otro las funciones públicas listadas en `API_CONTRATO.md §6`.
- `service.py` no conoce FastAPI: recibe `Session` y datos, lanza `app.core.errors.*`.
- Las fórmulas viven SOLO en `adpro/calculos.py` (puras, testeadas) y la consulta de precios en
  `adpro/valorizacion.py`.

## 3. Convenciones

| Elemento | Convención | Ejemplo |
|---|---|---|
| Tablas | `<modulo>_<entidad>` snake_case singular | `adpro_presupuesto_linea` |
| Restricciones | convención de nombres en `Base.metadata` | `uq_adpro_etapa_proyecto_id_codigo` |
| Clases de modelo | PascalCase español | `PresupuestoVersion` |
| Schemas | `<Entidad>Create`, `<Entidad>Update`, `<Entidad>Out`, `<Entidad>DetalleOut` | `InsumoCreate` |
| Services | verbos en español: `listar_*`, `obtener_*`, `crear_*`, `actualizar_*`, `eliminar_*` | `crear_insumo(db, data)` |
| Rutas | `/api/<modulo>/<submodulo>/<recurso-plural-kebab>` | `/api/adpro/maestros/listas-precios` |
| Enums | `str, Enum` con valores MAYÚSCULA (roles en minúscula) | `TipoInsumo.MAT` |
| Tests | `tests/<modulo>/<submodulo>/test_<tema>.py` | `tests/adpro/apu/test_valorizacion.py` |

### Números y redondeo
- Tipos de columna: `Money`/`Qty` = `Numeric(18,4)`, `Coef` = `Numeric(18,6)` (cantidades APU),
  `Pct` = `Numeric(9,6)` como **fracción** (0.19 = 19 %).
- Unitarios a 4 decimales; `valor_total` de línea redondeado a **pesos enteros** (ROUND_HALF_UP);
  AIU e IVA redondeados a pesos por componente. Ver `adpro/calculos.py`.
- Nunca `float`: en Python `Decimal`, en JSON string, en el frontend se formatea con `Intl.NumberFormat('es-CO')`.

### Fórmulas del dominio
- APU: `vu = Σ cantidad · (1 + desperdicio) · precio_vigente(insumo, ciudad, fecha)`.
- Precio vigente: lista activa de la ciudad con mayor `fecha_desde ≤ fecha` que contenga el insumo.
- Línea: `total = redondear(cantidad · vu)`. Costo directo = Σ totales.
- AIU: `A = CD·%A`, `I = CD·%I`, `U = CD·%U`, `IVA = U·%IVA`; Total = CD + A + I + U + IVA.
- Explosión: cantidad insumo = Σ `cant_línea · cant_unitaria · (1 + desperdicio)`; valor = cantidad · precio snapshot.
- Comparativo: `impacto = total_comparado − total_base`; `variación = impacto / total_base`.

## 4. Versionado inmutable de presupuestos

```
BORRADOR --aprobar (admin)--> APROBADO --cerrar (admin)--> CERRADO
    ^                              |
    +-------- copiar (nueva versión BORRADOR, version_origen_id) ----+
```

- Cada línea guarda su valor unitario y la **composición valorizada** (`adpro_presupuesto_linea_insumo`)
  al momento de crearse/recalcularse. Al aprobar, se congelan `total_costo_directo` y `total_presupuesto`.
- Aprobado/Cerrado ⇒ toda escritura sobre la versión o sus líneas responde 422 `BUSINESS_RULE`.
- Para cambiar algo aprobado: **copiar** la versión (opcionalmente revalorizando a nueva fecha).
- Tipos: `BASE`, `FIC`, `FIV`, `CONTROL`, `OTRO`. Compromisos y ejecución se asocian al
  **presupuesto** (no a la versión) y se cruzan por ítem contra la versión `CONTROL` aprobada vigente.
- Cada transición queda en `core_audit_log` (APROBAR, CERRAR, COPIAR, RECALCULAR, IMPORTAR, ANULAR).
- Defensa en profundidad: un listener `before_flush` relee el estado de la versión **en la BD**
  (con `FOR UPDATE`) y rechaza cualquier escritura sobre versiones no BORRADOR; la única
  transición permitida desde APROBADO es a CERRADO. Los services cargan la versión con
  `obtener_version_para_escritura` (bloqueo de fila), así editar y aprobar en paralelo quedan
  serializados en PostgreSQL (en SQLite las escrituras ya son serializadas).
- El tipo y la unidad de un insumo usado en versiones aprobadas/cerradas (unidad: usado en
  cualquier APU/presupuesto/compromiso) no se pueden cambiar: la explosión de una versión
  aprobada no cambia por editar el maestro. Mejora futura: guardar tipo/unidad en el snapshot
  `presupuesto_linea_insumo` y permitir reclasificar el maestro sin restricción.

## 5. Seguridad

- Prototipo: bcrypt + JWT HS256 (`JWT_SECRET` en `.env`), expiración 8 h, roles `admin`,
  `presupuesto`, `obra`, `consulta`. `require_role(...)` con ADMIN siempre autorizado.
- `get_current_user` deja el usuario en `Session.info`; un listener `before_flush` llena
  `created_by`/`updated_by` y `registrar_auditoria` toma el usuario de ahí.
- Producción: `AUTH_PROVIDER=entra` → `EntraIdProvider` valida el token de Entra ID (JWKS),
  aprovisiona el usuario por `oid` (`Usuario.external_id`) y mapea App Roles → `Rol`. Frontend con MSAL.
- Secretos solo por variables de entorno (en producción, Azure Key Vault). Fuera de
  `ENVIRONMENT` local/test se exige un `JWT_SECRET` propio de ≥ 32 caracteres (el arranque falla
  si falta); en local, si no se define, se genera uno aleatorio por máquina
  (`backend/.jwt_secret.local`, no versionado). `production` además rechaza SQLite.
- El seed no tiene contraseñas fijas: usa `DEV_*_PASSWORD` o genera una aleatoria y la imprime.
- docker-compose publica puertos solo en `127.0.0.1` (`BIND_ADDR`) y exige `JWT_SECRET`.
- Login: bcrypt se ejecuta aunque el usuario no exista (sin oráculo de tiempo). **Pendiente
  antes de exponer el auth local en red**: rate limiting por IP/usuario y bloqueo temporal (en
  producción lo cubre Entra ID).
- Exportaciones Excel: los textos de usuario nunca se escriben como fórmula (`excel.asignar_celda`).
- Errores de rango de la BD (`DataError`) → 422; enteros de entrada acotados a INTEGER (`Int32`)
  y valores monetarios a `Numeric(18,4)` (`calculos.asegurar_rango`).
- Fechas con hora: tipo `UTCDateTime` (UTC con zona en ambos motores).
- Pruebas contra PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://... pytest` (BD dedicada;
  la CI lo ejecuta en el job `backend-postgres`).
- Datos: el repositorio solo contiene datos **sintéticos**.

## 6. Cómo agregar un nuevo módulo (p. ej. `compras`)

1. Crear `backend/app/modules/compras/` con `__init__.py`, `models.py`, `enums.py` y un
   subpaquete por submódulo (`router.py`, `schemas.py`, `service.py`).
2. Tablas con prefijo `compras_`, heredando `TimestampMixin, Base`; tipos `Money/Qty/Pct`, `str_enum`.
3. Registrar los modelos en `app/db_models.py` y el router agregador en `app/main.py` (prefijo `/api/compras`).
4. `alembic revision --autogenerate -m "compras: ..."`, revisar el script y `alembic upgrade head`.
5. Documentar endpoints en `docs/API_CONTRATO.md` y tests en `tests/compras/...`.
6. Integraciones entre módulos: funciones de service públicas y documentadas (p. ej. compras
   crea compromisos en ADPRO llamando a `adpro.control.service.registrar_compromiso`), nunca
   escribiendo directamente tablas ajenas. A futuro, eventos de dominio (outbox) si se separan servicios.

## 7. Estrategia hacia producción (propuesta)

| Fase | Objetivo | Entregables | Criterio de salida |
|---|---|---|---|
| **0. Prototipo local** (actual) | Demostrar ADPRO end-to-end con datos sintéticos | Backend + SPA + seed demo + docs | Demo a directivos: crear presupuesto, APU, aprobar, comparar FIC vs FIV, tablero |
| **1. Piloto controlado** | 1 proyecto real en paralelo con el sistema actual | PostgreSQL gestionado, Entra ID, CI/CD, carga inicial ProdesaClass + listas de precios, backups | Cifras del piloto cuadran con el sistema actual (±0 en totales) |
| **2. Producción ADPRO** | Todos los proyectos nuevos en ADPRO | Hardening, monitoreo, soporte, capacitación | SLA acordado, auditoría de TI aprobada |
| **3. Módulos siguientes** | Compras → Contratos → Comercial → Tesorería → Contabilidad | Un módulo por trimestre sobre la misma plataforma | Integración contable validada |

**Plataforma sugerida (alineada con Microsoft 365/Entra ID)**:
- Azure Container Apps o App Service (contenedor del backend) + Static Web Apps (frontend).
- Azure Database for PostgreSQL Flexible Server (backups automáticos, PITR, réplica de lectura para BI/Power BI).
- Azure Key Vault (secretos), Entra ID (SSO + App Roles), Application Insights / OpenTelemetry (trazas, métricas).
- GitHub Actions: lint (ruff, eslint) + tests + `alembic upgrade --sql` de verificación + build de imagen + despliegue
  por ambientes (dev → staging → prod) con aprobación manual a prod. Ramas protegidas y PR obligatorio.
- Datos maestros: ETL de carga inicial desde Excel/exportaciones del sistema actual hacia las tablas `adpro_*`,
  con validaciones y bitácora; reconciliación de totales antes de cada corte.
- Analítica: vistas SQL/réplica de lectura consumidas por Power BI (no consultas directas a la BD transaccional).

**Escalabilidad técnica** (cuando haga falta, no antes):
- Paginación y filtros en servidor (ya en el contrato); índices definidos en modelos.
- Cálculos pesados (explosión de proyectos grandes, Excel masivos) → tareas en segundo plano (cola) y caché de resúmenes de versiones aprobadas (inmutables ⇒ cacheables sin invalidación).
- Multi-empresa/consorcios: agregar `empresa_id` a proyectos y filtros por tenant.
- Particionar en servicios solo el módulo con carga o ciclo de despliegue distinto.

## 8. Mejoras documentadas (fuera de v1)

- Sub-APU (APU que usan otros APU como insumo) y APU por ciudad/regional.
- Cantidades por torre/etapa en líneas de presupuesto y presupuesto por localización.
- Flujo de aprobación multinivel (director de obra → gerencia) con notificaciones (Teams/correo).
- Vinculación de compromisos con el módulo de compras/contratos y de ejecución con actas de obra.
- Curva S (programado vs ejecutado) e integración con cronograma.
- Integración BIM (cantidades desde modelos) y con ProdesaClass como catálogo maestro.
