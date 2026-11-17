# Contrato de API REST — ERP Prodesa / ADPRO (v0.1)

Este documento es la **fuente de verdad** que siguen en paralelo los agentes de backend
(maestros, apu, presupuesto, control) y el de frontend. Si un agente necesita cambiarlo,
lo reporta (no lo edita). Swagger vivo: `http://127.0.0.1:8000/docs`.

## 0. Convenciones generales

| Tema | Regla |
|---|---|
| Base URL | `http://127.0.0.1:8000` (frontend Vite: proxy `/api` → backend) |
| Auth | Header `Authorization: Bearer <access_token>` en todo excepto `/api/health`, `/api/auth/login`, `/api/auth/token` |
| Formato | JSON UTF-8. Nombres de campos en `snake_case` español |
| Decimales | Dinero, cantidades y porcentajes viajan como **string** (`"1250000.0000"`). En requests se aceptan string o número |
| Porcentajes | **Fracción**: `"0.05"` = 5 %. El frontend muestra ×100 |
| Fechas | `YYYY-MM-DD`; timestamps ISO-8601 con zona; periodos mensuales `YYYY-MM` |
| Enums | Strings en MAYÚSCULA (ver §0.2) |
| Listados paginados | `Page[T]` = `{"items": [T], "total": int, "limit": int, "offset": int}`; query `limit` (1–500, def. 50) y `offset` (def. 0) |
| Listados de catálogos pequeños | Lista JSON simple `[T]` (se indica en cada endpoint) |
| Crear | `201` + recurso creado. Actualizar: `200` + recurso. Eliminar: `204` sin cuerpo |
| PUT | Actualización **parcial** (solo campos enviados), salvo donde dice "reemplaza" |
| Campos de auditoría | Todo `*Out` de entidades con auditoría incluye `created_at, updated_at, created_by, updated_by` (omitidos abajo por brevedad) |
| Excel | Respuesta `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` con `Content-Disposition: attachment; filename="..."` |

### 0.1 Errores

Siempre con este cuerpo:

```json
{"error": {"code": "NOT_FOUND", "message": "Texto para el usuario", "details": null}}
```

| HTTP | code | Cuándo |
|---|---|---|
| 401 | `UNAUTHORIZED`, `INVALID_CREDENTIALS`, `TOKEN_INVALID`, `TOKEN_EXPIRED` | Sin token / token malo / login fallido |
| 403 | `FORBIDDEN` | Rol insuficiente (`details.requerido`, `details.actual`) |
| 404 | `NOT_FOUND` | Recurso no existe |
| 409 | `CONFLICT`, `INTEGRITY_ERROR` | Código duplicado, referencia en uso |
| 422 | `VALIDATION_ERROR` | Esquema inválido (`details` = lista `{loc, msg, type}`) |
| 422 | `BUSINESS_RULE` | Regla de negocio (p. ej. versión no editable) |

### 0.2 Enumeraciones

| Enum | Valores |
|---|---|
| `Rol` | `admin`, `presupuesto`, `obra`, `consulta` (minúscula) |
| `TipoInsumo` | `MAT` material, `MO` mano de obra, `EQ` equipo, `TR` transporte, `SUB` subcontrato |
| `TipoProyecto` | `VIS`, `VIP`, `NO_VIS` |
| `EstadoProyecto` | `PLANEACION`, `EN_EJECUCION`, `TERMINADO`, `SUSPENDIDO` |
| `NivelEdt` | `CAPITULO`, `DETALLE`, `GRUPO`, `ITEM` |
| `TipoVersion` | `BASE`, `FIC`, `FIV`, `CONTROL`, `OTRO` |
| `EstadoVersion` | `BORRADOR`, `APROBADO`, `CERRADO` |
| `OrigenValor` | `APU`, `MANUAL`, `IMPORTADO` |
| `TipoCompromiso` | `ORDEN_COMPRA`, `CONTRATO`, `ORDEN_SERVICIO` |
| `EstadoCompromiso` | `VIGENTE`, `LIQUIDADO`, `ANULADO` |

### 0.3 Roles (columna "Rol" de las tablas)

| Código | Roles permitidos | Constante en `app.core.security` |
|---|---|---|
| **L** (lectura) | cualquier usuario autenticado | `CurrentUser` |
| **M** (maestros) | admin, presupuesto | `ROLES_ESCRITURA_MAESTROS` |
| **P** (presupuesto) | admin, presupuesto | `ROLES_ESCRITURA_PRESUPUESTO` |
| **A** (aprobación) | admin | `ROLES_APROBACION` |
| **C** (control) | admin, presupuesto, obra | `ROLES_ESCRITURA_CONTROL` |

Uso: `dependencies=[Depends(require_role(*ROLES_ESCRITURA_MAESTROS))]`.

---

> **Rutas**: en las secciones 2 a 5 las rutas de las tablas son relativas a `/api/adpro`
> (p. ej. `/maestros/unidades` = `GET /api/adpro/maestros/unidades`). La sección 1 usa rutas absolutas.

## 1. Sistema y autenticación (`app/core` — ya implementado)

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/api/health` | — | `{status, app, version, environment, database}` | público |
| POST | `/api/auth/login` | `{username, password}` | `TokenResponse` | público |
| POST | `/api/auth/token` | form `username`, `password` (OAuth2, para Swagger) | `TokenResponse` | público |
| GET | `/api/auth/me` | — | `UsuarioOut` | L |
| GET | `/api/auditoria?entidad&entidad_id&limit&offset` | — | `Page[AuditLogOut]` | A |

- `TokenResponse` = `{access_token, token_type:"bearer", expires_in (s), user: UsuarioOut}`
- `UsuarioOut` = `{id, username, nombre, email, rol, activo}`
- `AuditLogOut` = `{id, timestamp, username, accion, entidad, entidad_id, detalle}`

El frontend guarda el token (memoria + `sessionStorage`), lo envía en cada request y ante
`401` redirige a login. En producción el login pasa a Microsoft Entra ID (MSAL) y el backend
valida el token de Entra: **el resto del contrato no cambia**.

---

## 2. Maestros — `/api/adpro/maestros` (zona: `app/modules/adpro/maestros/`)

### 2.1 Unidades y ciudades (catálogos pequeños, lista simple)

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/maestros/unidades?q&activo` | — | `[UnidadOut]` (orden `codigo`) | L |
| POST | `/maestros/unidades` | `UnidadCreate` | `UnidadOut` 201 | M |
| PUT | `/maestros/unidades/{id}` | `UnidadUpdate` | `UnidadOut` | M |
| GET | `/maestros/ciudades?q&activo` | — | `[CiudadOut]` | L |
| POST | `/maestros/ciudades` | `CiudadCreate` | `CiudadOut` 201 | M |
| PUT | `/maestros/ciudades/{id}` | `CiudadUpdate` | `CiudadOut` | M |

- `UnidadOut` = `{id, codigo, nombre, activo}`; `UnidadCreate` = `{codigo, nombre, activo?=true}`
- `CiudadOut` = `{id, codigo, nombre, departamento, regional, activo}`; `CiudadCreate` igual sin `id`
- No hay DELETE: se inactiva (`activo=false`). `codigo` se normaliza a MAYÚSCULAS; duplicado → 409.

### 2.2 Insumos

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/maestros/insumos?q&tipo&activo&unidad_id&limit&offset` | — | `Page[InsumoOut]` (orden `codigo`; `q` busca en código y descripción) | L |
| GET | `/maestros/insumos/{id}` | — | `InsumoOut` | L |
| POST | `/maestros/insumos` | `InsumoCreate` | `InsumoOut` 201 | M |
| PUT | `/maestros/insumos/{id}` | `InsumoUpdate` | `InsumoOut` | M |
| GET | `/maestros/insumos/{id}/precios?ciudad_id` | — | `[PrecioHistoricoOut]` (orden ciudad, `fecha_desde` desc) | L |

- `InsumoOut` = `{id, codigo, descripcion, unidad_id, unidad_codigo, tipo, activo, observaciones}`
- `InsumoCreate` = `{codigo, descripcion, unidad_id, tipo, activo?=true, observaciones?}`
- `InsumoUpdate` = todos opcionales excepto que `codigo` NO se puede cambiar si el insumo está en un APU o presupuesto (422).
- `PrecioHistoricoOut` = `{lista_id, lista_codigo, lista_nombre, ciudad_id, ciudad_codigo, fecha_desde, precio}`

### 2.3 Listas de precios (con vigencia por ciudad, histórico)

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/maestros/listas-precios?ciudad_id&activo` | — | `[ListaPreciosOut]` (orden ciudad, `fecha_desde` desc) | L |
| POST | `/maestros/listas-precios` | `ListaPreciosCreate` | `ListaPreciosOut` 201 | M |
| GET | `/maestros/listas-precios/{id}` | — | `ListaPreciosOut` | L |
| PUT | `/maestros/listas-precios/{id}` | `ListaPreciosUpdate` | `ListaPreciosOut` | M |
| GET | `/maestros/listas-precios/{id}/precios?q&tipo&limit&offset` | — | `Page[PrecioOut]` | L |
| PUT | `/maestros/listas-precios/{id}/precios` | `{precios: [PrecioIn]}` (upsert por `insumo_id`) | `{creados, actualizados}` | M |
| DELETE | `/maestros/listas-precios/{id}/precios/{insumo_id}` | — | 204 | M |
| GET | `/maestros/precios-vigentes?ciudad_id&fecha&insumo_ids=1,2,3` | — | `[PrecioVigenteOut]` | L |

- `ListaPreciosOut` = `{id, codigo, nombre, ciudad_id, ciudad_codigo, fecha_desde, activo, observaciones, num_precios}`
- `ListaPreciosCreate` = `{codigo, nombre, ciudad_id, fecha_desde, observaciones?, copiar_de_lista_id?}` — si viene `copiar_de_lista_id` copia todos sus precios (flujo típico: nueva vigencia a partir de la anterior). Única por (`ciudad_id`, `fecha_desde`) → 409.
- `ListaPreciosUpdate` = `{nombre?, activo?, observaciones?}` (ciudad y fecha son inmutables).
- `PrecioIn` = `{insumo_id, precio, fuente?}` (precio ≥ 0); `PrecioOut` = `{id, insumo_id, insumo_codigo, insumo_descripcion, unidad_codigo, tipo, precio, fuente}`
- `PrecioVigenteOut` = `{insumo_id, precio, lista_id, fecha_desde}`; usa `app.modules.adpro.valorizacion.precios_vigentes`. Insumos sin precio no aparecen.

### 2.4 Proyectos, etapas y torres

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/maestros/proyectos?q&estado&tipo&ciudad_id` | — | `[ProyectoOut]` (orden `codigo`) | L |
| POST | `/maestros/proyectos` | `ProyectoCreate` | `ProyectoDetalleOut` 201 | M |
| GET | `/maestros/proyectos/{id}` | — | `ProyectoDetalleOut` | L |
| PUT | `/maestros/proyectos/{id}` | `ProyectoUpdate` | `ProyectoDetalleOut` | M |
| POST | `/maestros/proyectos/{id}/etapas` | `EtapaCreate` | `EtapaOut` 201 | M |
| PUT | `/maestros/etapas/{id}` | `EtapaUpdate` | `EtapaOut` | M |
| DELETE | `/maestros/etapas/{id}` | — | 204 (409 si tiene presupuestos) | M |
| POST | `/maestros/etapas/{id}/torres` | `TorreCreate` | `TorreOut` 201 | M |
| PUT | `/maestros/torres/{id}` | `TorreUpdate` | `TorreOut` | M |
| DELETE | `/maestros/torres/{id}` | — | 204 | M |

- `ProyectoOut` = `{id, codigo, nombre, ciudad_id, ciudad_codigo, ciudad_nombre, tipo, estado, fecha_inicio, fecha_fin_estimada, numero_unidades, descripcion}`
- `ProyectoDetalleOut` = `ProyectoOut + {etapas: [EtapaOut]}`
- `EtapaOut` = `{id, proyecto_id, codigo, nombre, orden, numero_unidades, torres: [TorreOut]}`
- `TorreOut` = `{id, etapa_id, codigo, nombre, numero_pisos, numero_unidades}`
- `ProyectoCreate` = `{codigo, nombre, ciudad_id, tipo, estado?=PLANEACION, fecha_inicio?, fecha_fin_estimada?, numero_unidades?, descripcion?}`; Update = parcial (sin `codigo`).
- `EtapaCreate` = `{codigo, nombre, orden?=0, numero_unidades?}`; `TorreCreate` = `{codigo, nombre, numero_pisos?, numero_unidades?}`.

### 2.5 EDT presupuestal (catálogo estilo ProdesaClass)

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/maestros/edt?nivel&parent_id&q&activo&limit&offset` | — | `Page[EdtNodoOut]` (orden `codigo`) | L |
| GET | `/maestros/edt/arbol?capitulo_id&hasta_nivel=ITEM&activo` | — | `[EdtArbolNodo]` (raíces = capítulos) | L |
| GET | `/maestros/edt/{id}` | — | `EdtNodoDetalleOut` | L |
| POST | `/maestros/edt` | `EdtNodoCreate` | `EdtNodoOut` 201 | M |
| PUT | `/maestros/edt/{id}` | `EdtNodoUpdate` | `EdtNodoOut` | M |

- `EdtNodoOut` = `{id, parent_id, nivel, codigo, descripcion, unidad_id, unidad_codigo, orden, activo, notas, tiene_apu}`
- `EdtArbolNodo` = `EdtNodoOut + {hijos: [EdtArbolNodo]}`
- `EdtNodoDetalleOut` = `EdtNodoOut + {ruta: [{id, nivel, codigo, descripcion}]}` (de capítulo al nodo, para breadcrumbs)
- `EdtNodoCreate` = `{parent_id?, nivel, codigo, descripcion, unidad_id?, orden?, notas?}`. Reglas (422 `BUSINESS_RULE`):
  CAPITULO sin padre; DETALLE→padre CAPITULO; GRUPO→padre DETALLE; ITEM→padre GRUPO y `unidad_id` obligatorio; niveles ≠ ITEM sin unidad.
  Código recomendado `CC`, `CC.DD`, `CC.DD.GGG`, `CC.DD.GGG.IIII` y debe empezar por el código del padre + `.`.
- `EdtNodoUpdate` = `{descripcion?, unidad_id?, orden?, activo?, notas?}` (`codigo`, `nivel`, `parent_id` inmutables en v1).

---

## 3. APU — `/api/adpro/apu` (zona: `app/modules/adpro/apu/`)

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/apu/apus?q&capitulo_id&activo&limit&offset` | — | `Page[ApuOut]` (orden código del ítem) | L |
| GET | `/apu/apus/{id}` | — | `ApuDetalleOut` | L |
| GET | `/apu/apus/por-item/{item_id}` | — | `ApuDetalleOut` (404 si el ítem no tiene APU) | L |
| POST | `/apu/apus` | `ApuCreate` | `ApuDetalleOut` 201 | M |
| PUT | `/apu/apus/{id}` | `ApuUpdate` | `ApuDetalleOut` | M |
| PUT | `/apu/apus/{id}/insumos` | `{insumos: [ApuInsumoIn]}` (**reemplaza** la composición) | `ApuDetalleOut` | M |
| POST | `/apu/apus/{id}/insumos` | `ApuInsumoIn` | `ApuInsumoOut` 201 | M |
| PUT | `/apu/apus/{id}/insumos/{apu_insumo_id}` | `ApuInsumoUpdate` | `ApuInsumoOut` | M |
| DELETE | `/apu/apus/{id}/insumos/{apu_insumo_id}` | — | 204 | M |
| POST | `/apu/apus/{id}/copiar` | `{item_id_destino, descripcion?}` | `ApuDetalleOut` 201 | M |
| GET | `/apu/apus/{id}/valorizacion?ciudad_id&fecha` | — | `ValorizacionOut` | L |

- `ApuOut` = `{id, item_id, item_codigo, item_descripcion, unidad_codigo, descripcion, activo, observaciones, num_insumos}`
- `ApuDetalleOut` = `ApuOut + {insumos: [ApuInsumoOut]}`
- `ApuInsumoOut` = `{id, insumo_id, insumo_codigo, insumo_descripcion, unidad_codigo, tipo, cantidad, desperdicio_pct, orden, observacion}`
- `ApuCreate` = `{item_id, descripcion?, observaciones?, insumos: [ApuInsumoIn] = []}`; el ítem debe ser nivel ITEM y no tener APU (409).
- `ApuInsumoIn` = `{insumo_id, cantidad (≥0, hasta 6 decimales), desperdicio_pct? = "0", orden?, observacion?}`; insumo repetido en el mismo APU → 409; insumo inactivo → 422.
- `ApuInsumoUpdate` = `{cantidad?, desperdicio_pct?, orden?, observacion?}`
- `ValorizacionOut` = `{apu_id, item_id, ciudad_id, fecha, valor_unitario, insumos_sin_precio: [insumo_id], subtotales_por_tipo: {"MAT": "…", "MO": "…", …}, componentes: [ComponenteOut]}`
- `ComponenteOut` = `{insumo_id, insumo_codigo, insumo_descripcion, unidad_codigo, tipo, cantidad, desperdicio_pct, precio_unitario, valor_unitario, precio_faltante, lista_id}`
- Fórmula: `valor_unitario = Σ cantidad·(1+desperdicio_pct)·precio_vigente` → usar `app.modules.adpro.valorizacion.valorizar_apu`.
- Cambiar un APU **no** altera versiones de presupuesto existentes (tienen snapshot); las BORRADOR se actualizan con `POST .../recalcular`.

---

## 4. Presupuesto — `/api/adpro/presupuestos` (zona: `app/modules/adpro/presupuesto/`)

### 4.1 Presupuestos

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/presupuestos?proyecto_id&q` | — | `[PresupuestoOut]` | L |
| POST | `/presupuestos` | `PresupuestoCreate` | `PresupuestoDetalleOut` 201 | P |
| GET | `/presupuestos/{id}` | — | `PresupuestoDetalleOut` | L |
| PUT | `/presupuestos/{id}` | `{nombre?, descripcion?}` | `PresupuestoDetalleOut` | P |

- `PresupuestoOut` = `{id, proyecto_id, proyecto_codigo, proyecto_nombre, etapa_id, etapa_codigo, codigo, nombre, descripcion, num_versiones}`
- `PresupuestoDetalleOut` = `PresupuestoOut + {versiones: [VersionOut]}` (orden `numero`)
- `PresupuestoCreate` = `{proyecto_id, etapa_id?, codigo, nombre, descripcion?}` (etapa debe ser del proyecto; único por proyecto+código → 409)

### 4.2 Versiones (ciclo BORRADOR → APROBADO → CERRADO)

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| POST | `/presupuestos/{id}/versiones` | `VersionCreate` | `VersionOut` 201 (BORRADOR, `numero` consecutivo) | P |
| GET | `/presupuestos/versiones/{vid}` | — | `VersionOut` | L |
| PUT | `/presupuestos/versiones/{vid}` | `VersionUpdate` | `VersionOut` | P |
| DELETE | `/presupuestos/versiones/{vid}` | — | 204 (solo BORRADOR) | P |
| POST | `/presupuestos/versiones/{vid}/aprobar` | `{observacion?}` | `VersionOut` | A |
| POST | `/presupuestos/versiones/{vid}/cerrar` | `{observacion?}` | `VersionOut` | A |
| POST | `/presupuestos/versiones/{vid}/copiar` | `VersionCopy` | `VersionOut` 201 (nuevo BORRADOR) | P |
| POST | `/presupuestos/versiones/{vid}/recalcular` | `{}` | `RecalculoOut` | P |

- `VersionOut` = `{id, presupuesto_id, numero, tipo, estado, nombre, descripcion, fecha_precios, ciudad_precios_id, ciudad_precios_codigo, administracion_pct, imprevistos_pct, utilidad_pct, iva_utilidad_pct, version_origen_id, aprobado_at, aprobado_por, cerrado_at, cerrado_por, total_costo_directo, total_presupuesto, num_lineas, editable}`
  (`total_*`: congelados si APROBADO/CERRADO; calculados al vuelo si BORRADOR)
- `VersionCreate` = `{tipo, nombre, descripcion?, fecha_precios, ciudad_precios_id? (def. ciudad del proyecto), administracion_pct?="0", imprevistos_pct?="0", utilidad_pct?="0", iva_utilidad_pct?="0.19"}`
- `VersionUpdate` = mismos campos opcionales (sin `tipo`). Solo BORRADOR (si no → 422 `BUSINESS_RULE`). Cambiar fecha/ciudad NO recalcula: el cliente llama `recalcular`.
- **aprobar**: exige BORRADOR y ≥1 línea; congela `total_costo_directo` y `total_presupuesto`, `aprobado_at/por`; audita `APROBAR`. Desde ahí la versión y sus líneas son inmutables (toda escritura → 422).
- **cerrar**: exige APROBADO; audita `CERRAR`.
- `VersionCopy` = `{tipo, nombre, descripcion?, presupuesto_id_destino? (def. mismo), recalcular_precios?=false, fecha_precios?}` — copia AIU, líneas y snapshot de insumos; `version_origen_id` = origen; si `recalcular_precios`, revaloriza líneas de origen APU a la nueva fecha. Audita `COPIAR`.
- `RecalculoOut` = `{version_id, lineas_recalculadas, insumos_sin_precio: [insumo_id], total_costo_directo}` — solo BORRADOR; revaloriza líneas con `origen_unitario=APU` (regenera snapshot desde el APU vigente). Audita `RECALCULAR`.

### 4.3 Líneas

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/presupuestos/versiones/{vid}/lineas?capitulo_id&q` | — | `[LineaOut]` (orden código ítem) | L |
| POST | `/presupuestos/versiones/{vid}/lineas` | `LineaCreate` | `LineaOut` 201 | P |
| POST | `/presupuestos/versiones/{vid}/lineas/lote` | `{lineas: [LineaCreate]}` | `{creadas, errores: [{indice, mensaje}]}` (todo o nada) | P |
| PUT | `/presupuestos/versiones/{vid}/lineas/{lid}` | `LineaUpdate` | `LineaOut` | P |
| DELETE | `/presupuestos/versiones/{vid}/lineas/{lid}` | — | 204 | P |
| GET | `/presupuestos/versiones/{vid}/lineas/{lid}/insumos` | — | `[LineaInsumoOut]` | L |

- `LineaOut` = `{id, version_id, item_id, item_codigo, item_descripcion, unidad_codigo, capitulo_id, capitulo_codigo, capitulo_descripcion, cantidad, valor_unitario, valor_total, origen_unitario, orden, observacion, num_insumos, insumos_sin_precio}`
- `LineaCreate` = `{item_id, cantidad, valor_unitario?, observacion?}`:
  - sin `valor_unitario` → valoriza el APU del ítem a `fecha_precios`/`ciudad_precios` de la versión, guarda snapshot en `presupuesto_linea_insumo`, `origen_unitario=APU`; si el ítem no tiene APU → 422.
  - con `valor_unitario` → `origen_unitario=MANUAL`, sin snapshot.
  - ítem repetido en la versión → 409. `valor_total = redondear_pesos(cantidad·valor_unitario)`.
- `LineaUpdate` = `{cantidad?, valor_unitario?, observacion?, orden?}` (enviar `valor_unitario` la vuelve MANUAL y borra el snapshot).
- `LineaInsumoOut` = `{insumo_id, insumo_codigo, insumo_descripcion, unidad_codigo, tipo, cantidad_unitaria, desperdicio_pct, precio_unitario, valor_unitario, precio_faltante, cantidad_total, valor_total}`

### 4.4 Resumen (AIU) y explosión de insumos

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/presupuestos/versiones/{vid}/resumen` | — | `ResumenOut` | L |
| GET | `/presupuestos/versiones/{vid}/explosion?tipo` | — | `ExplosionOut` | L |

- `ResumenOut` = `{version_id, capitulos: [CapituloTotal], costo_directo, administracion_pct, imprevistos_pct, utilidad_pct, iva_utilidad_pct, administracion, imprevistos, utilidad, iva_utilidad, total_aiu, total, num_lineas, lineas_sin_precio}`
- `CapituloTotal` = `{capitulo_id, codigo, descripcion, valor, participacion_pct, num_lineas}`
- `ExplosionOut` = `{version_id, filas: [ExplosionFila], por_tipo: [{tipo, valor_total, participacion_pct}], total_insumos, valor_sin_desglose, total}`
  - `ExplosionFila` = `{insumo_id, insumo_codigo, insumo_descripcion, unidad_codigo, tipo, cantidad_total, precio_unitario, valor_total, participacion_pct}` (`precio_unitario` = `valor_total / cantidad_total`).
  - `valor_sin_desglose` = suma de líneas MANUAL/IMPORTADO sin snapshot (para cuadrar contra el costo directo).
- Fórmulas: `app.modules.adpro.calculos` (`calcular_aiu`, `cantidad_total_insumo`, `valor_total_insumo`).

---

## 5. Control — `/api/adpro/control` (zona: `app/modules/adpro/control/`)

### 5.1 Comparativo entre versiones

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/control/comparativo?version_base_id&version_comparada_id&nivel=item` | — | `ComparativoOut` | L |

- `nivel` ∈ `item` (def.), `insumo`, `capitulo`. Las versiones pueden ser de presupuestos distintos (p. ej. FIC vs FIV).
- `ComparativoOut` = `{version_base: VersionRef, version_comparada: VersionRef, nivel, filas: [ComparativoFila], totales: {total_base, total_comparado, impacto, variacion_pct}}`
- `VersionRef` = `{id, presupuesto_id, numero, nombre, tipo, estado}`
- `ComparativoFila` = `{clave_id, codigo, descripcion, unidad_codigo, tipo (solo insumo), capitulo_codigo, cantidad_base, cantidad_comparada, unitario_base, unitario_comparado, total_base, total_comparado, diferencia_cantidad, diferencia_unitaria, impacto, variacion_pct, estado}`
  - `diferencia_unitaria = unitario_comparado − unitario_base`; `impacto = total_comparado − total_base`;
    `variacion_pct = impacto / total_base` (null si base = 0) → `calculos.variacion_pct`.
  - `estado` ∈ `IGUAL`, `MODIFICADO`, `NUEVO` (solo en comparada), `ELIMINADO` (solo en base).
  - Nivel `insumo`: usa el snapshot `presupuesto_linea_insumo` (cantidad total y valor por insumo, como la explosión).

### 5.2 Compromisos (órdenes / contratos simplificados)

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/control/compromisos?presupuesto_id&estado&tipo&item_id&q&limit&offset` | — | `Page[CompromisoOut]` | L |
| POST | `/control/compromisos` | `CompromisoCreate` | `CompromisoDetalleOut` 201 | C |
| GET | `/control/compromisos/{id}` | — | `CompromisoDetalleOut` | L |
| PUT | `/control/compromisos/{id}` | `CompromisoUpdate` (si trae `lineas`, **reemplaza**) | `CompromisoDetalleOut` | C |
| POST | `/control/compromisos/{id}/anular` | `{motivo}` | `CompromisoDetalleOut` | C |
| POST | `/control/compromisos/{id}/liquidar` | `{}` | `CompromisoDetalleOut` | C |

- `CompromisoOut` = `{id, presupuesto_id, tipo, numero, fecha, tercero, descripcion, estado, valor_total, num_lineas}`
- `CompromisoDetalleOut` = `CompromisoOut + {lineas: [CompromisoLineaOut], advertencias: [str]}`
- `CompromisoLineaOut` = `{id, item_id, item_codigo, item_descripcion, insumo_id, insumo_codigo, descripcion, cantidad, valor_unitario, valor_total}`
- `CompromisoCreate` = `{presupuesto_id, tipo, numero, fecha, tercero, descripcion?, lineas: [{item_id, insumo_id?, descripcion?, cantidad, valor_unitario}] (≥1)}`; `valor_total` de línea = `redondear_pesos(cantidad·valor_unitario)`; del compromiso = Σ líneas. Único (`presupuesto_id`, `tipo`, `numero`) → 409. `advertencias` si un ítem no está en la versión de control o si lo comprometido supera lo presupuestado.
- Solo VIGENTE es editable; ANULADO no suma en tablero. `tercero` = SOLO nombres ficticios.

### 5.3 Ejecución / avance mensual

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/control/ejecucion?presupuesto_id&periodo&item_id&desde&hasta` | — | `[EjecucionOut]` | L |
| GET | `/control/ejecucion/periodos?presupuesto_id` | — | `["2026-09", "2026-10", …]` | L |
| PUT | `/control/ejecucion` | `EjecucionLote` (upsert por presupuesto+ítem+periodo) | `{creados, actualizados, advertencias}` | C |
| DELETE | `/control/ejecucion/{id}` | — | 204 | C |

- `EjecucionOut` = `{id, presupuesto_id, item_id, item_codigo, item_descripcion, periodo, valor_ejecutado, cantidad_ejecutada, avance_fisico_pct, compromiso_id, observacion}`
- `EjecucionLote` = `{presupuesto_id, periodo, registros: [{item_id, valor_ejecutado, cantidad_ejecutada?, avance_fisico_pct, compromiso_id?, observacion?}]}`
- Semántica: `valor_ejecutado`/`cantidad_ejecutada` = lo del **periodo**; `avance_fisico_pct` = **acumulado** al cierre (0..1). Advertencia si el avance baja frente al periodo anterior.

### 5.4 Tablero presupuesto vs comprometido vs ejecutado

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/control/tablero?presupuesto_id&version_id&periodo_hasta` | — | `TableroOut` | L |
| GET | `/control/tablero/items?presupuesto_id&version_id&capitulo_id&periodo_hasta` | — | `[TableroFila]` (por ítem) | L |

- `version_id` por defecto: última versión `CONTROL` APROBADA del presupuesto; si no hay, la última APROBADA; si no hay ninguna → 422.
- `TableroOut` = `{presupuesto_id, version: VersionRef, periodo_hasta, capitulos: [TableroFila], totales: TableroFila, serie_mensual: [{periodo, ejecutado, ejecutado_acumulado}]}`
- `TableroFila` = `{id, codigo, descripcion, presupuestado, comprometido, ejecutado, por_comprometer, saldo, pct_comprometido, pct_ejecutado, avance_fisico_pct}`
  - `presupuestado` = Σ `valor_total` de líneas (costo directo, sin AIU); `comprometido` = Σ líneas de compromisos no ANULADOS; `ejecutado` = Σ `valor_ejecutado` hasta `periodo_hasta`;
    `por_comprometer = presupuestado − comprometido`; `saldo = presupuestado − ejecutado`;
    `avance_fisico_pct` = promedio del último avance de cada ítem ponderado por su valor presupuestado.

### 5.5 Excel (importación / exportación)

| Método | Ruta | Request | Response | Rol |
|---|---|---|---|---|
| GET | `/control/excel/plantilla-presupuesto` | — | xlsx | L |
| POST | `/control/excel/presupuesto/{version_id}/importar?modo=agregar` | multipart `file` (.xlsx) | `ImportResultado` | P |
| GET | `/control/excel/presupuesto/{version_id}` | — | xlsx (hojas `Resumen`, `Presupuesto`) | L |
| GET | `/control/excel/explosion/{version_id}` | — | xlsx (hojas `Explosion`, `PorTipo`) | L |
| GET | `/control/excel/comparativo?version_base_id&version_comparada_id&nivel` | — | xlsx | L |

- Plantilla, hoja `Presupuesto`, fila 1 = encabezados exactos:
  `codigo_item | descripcion | unidad | cantidad | valor_unitario | observacion`
  (`descripcion`/`unidad` informativas; `valor_unitario` vacío = tomar del APU; con valor = `IMPORTADO`).
- `modo` ∈ `agregar` (def.: crea nuevas, actualiza existentes) | `reemplazar` (borra las líneas y carga).
- **Todo o nada**: si hay errores no se aplica nada.
  `ImportResultado` = `{aplicado, lineas_creadas, lineas_actualizadas, lineas_eliminadas, errores: [{fila, columna, mensaje}], advertencias: [str]}`. Solo versiones BORRADOR. Audita `IMPORTAR`.

---

## 6. Contratos internos entre submódulos (Python)

Para trabajar en paralelo, estas firmas son estables. Se puede programar contra ellas aunque el
otro agente aún no termine; el dueño DEBE implementarlas exactamente así.

| Proveedor | Firma | Consumidores |
|---|---|---|
| fundación (`calculos.py`) | `redondear_pesos, q4, valor_componente, valor_unitario_apu, valor_total_linea, cantidad_total_insumo, valor_total_insumo, calcular_aiu, variacion_pct, es_periodo_valido` | todos |
| fundación (`valorizacion.py`) | `precios_vigentes(db, insumo_ids, ciudad_id, fecha)`, `precio_vigente(...)`, `valorizar_apu(db, apu, ciudad_id, fecha) -> ValorizacionApu` | maestros, apu, presupuesto |
| presupuesto | `obtener_version(db, version_id) -> PresupuestoVersion` (404) | control |
| presupuesto | `asegurar_editable(version) -> None` (422 si no es BORRADOR) | control |
| presupuesto | `calcular_resumen(db, version_id) -> schemas.ResumenOut` | control (Excel) |
| presupuesto | `calcular_explosion(db, version_id, tipo: TipoInsumo \| None = None) -> schemas.ExplosionOut` | control (Excel, comparativo) |
| presupuesto | `aplicar_lineas(db, version_id, lineas: list[schemas.LineaCreate], *, modo: Literal["agregar","reemplazar"], origen_manual: OrigenValor = OrigenValor.MANUAL, commit: bool = True) -> dict[str, int]` (`{creadas, actualizadas, eliminadas}`; lanza `BusinessRuleError` con `details` por línea) | control (importación) |
| control | `comparar_versiones(db, base_id, comparada_id, nivel) -> schemas.ComparativoOut` | control (Excel) |

Regla: los routers nunca importan services de otro submódulo; solo los services pueden hacerlo,
y únicamente usando las funciones de esta tabla.
