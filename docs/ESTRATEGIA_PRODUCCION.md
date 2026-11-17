# Estrategia de producción — ERP Prodesa

> Cómo llevar el prototipo local de ADPRO a un sistema de producción seguro, auditable y
> escalable, y cómo crecer hacia un ERP completo sin poner en riesgo la operación.
> Documento de trabajo para TI, Presupuestos, Finanzas y la Dirección. Complementa
> [ARQUITECTURA.md](ARQUITECTURA.md) (decisiones técnicas) y [ROADMAP.md](ROADMAP.md) (fases).
> Las cifras de tiempo y costo son **rangos indicativos** con supuestos explícitos (§14), no cotizaciones.

---

## 1. Resumen y recomendación

**Recomendación: sustitución gradual, módulo por módulo, empezando por lo que diferencia a
Prodesa, con operación en paralelo y criterios de salida medibles.** No a un reemplazo total de
una sola vez.

1. **Construir lo diferencial**: presupuesto y control de obra (ADPRO), integrado con
   ProdesaClass, BIM/ACC y Power BI. Ahí un desarrollo propio da ventaja: refleja los procesos
   de Prodesa (versiones BASE/FIC/FIV/CONTROL, comparativos, EDT corporativa) y evita
   adaptaciones costosas de un producto genérico.
2. **Integrar o comprar lo regulado y estandarizado**: facturación electrónica, nómina
   electrónica y documento soporte se hacen **siempre** a través de un proveedor tecnológico
   habilitado por la DIAN. Para contabilidad NIIF y nómina, decidir en la Fase 4 con un análisis
   comprar o construir (§11). Rehacer desde cero un motor contable o de nómina tiene alto
   riesgo regulatorio y aporta poca diferenciación.
3. **Sinco sigue siendo el sistema de registro** de cada proceso mientras el módulo propio que
   lo reemplaza no cumpla sus criterios de salida (§9). Antes de extraer cualquier dato de Sinco
   se hace una **revisión jurídica del contrato de licencia** (§8.1).
4. **Plataforma en Azure** alineada con Microsoft 365 / Entra ID: menos fricción con TI, SSO
   inmediato y servicios gestionados (sin servidores que administrar).
5. **Desarrollo asistido por agentes de IA** con revisión humana obligatoria: equipo pequeño y
   productivo, con controles de calidad automáticos (§12).

---

## 2. Punto de partida (prototipo v0.1)

| Aspecto | Estado del prototipo | Brecha para producción |
|---|---|---|
| Arquitectura | Monolito modular FastAPI + React; contrato de API; módulo ADPRO completo | Ninguna estructural: el diseño ya prevé producción |
| Base de datos | SQLite local; PostgreSQL 16 vía Docker probado en CI | PostgreSQL gestionado con alta disponibilidad, backups y PITR |
| Identidad | JWT local con 4 roles | Entra ID (SSO + MFA) con App Roles; interfaz ya preparada (`AUTH_PROVIDER=entra`) |
| Datos | 100 % sintéticos (seed demo) | Carga inicial real (maestros, ProdesaClass, presupuestos vigentes) con conciliación |
| Auditoría | Campos `created/updated_*` + `core_audit_log` | Retención, inmutabilidad (exportación WORM) y consulta para Auditoría/Revisoría |
| Operación | Scripts locales, CI (lint, tests, migraciones en PostgreSQL, imágenes) | CD por ambientes, monitoreo, alertas, mesa de ayuda, DR probado |

---

## 3. Arquitectura objetivo en Azure

```
 Usuarios Prodesa (navegador, Teams)
          |  HTTPS + SSO (Entra ID, MFA, acceso condicional)
          v
 Azure Front Door + WAF ------------------------------+
          |                                            |
          v                                            v
 Static Web Apps / Container App "frontend"    Container App "backend" (FastAPI, N réplicas)
 (SPA React)                                   |  identidad administrada (sin contraseñas)
                                               |-- Azure Database for PostgreSQL Flexible Server
                                               |     (zona redundante, PITR, backup geo-redundante,
                                               |      réplica de lectura para BI)
                                               |-- Azure Key Vault (secretos, certificados)
                                               |-- Azure Blob Storage (Excel importados/exportados,
                                               |     adjuntos; versionado + soft delete; WORM para auditoría)
                                               |-- Container Apps Job (migraciones Alembic, tareas programadas)
                                               '-- Application Insights / Log Analytics (OpenTelemetry)

 Integraciones: ProdesaClass (catálogo EDT) | Power BI (réplica de lectura / vistas) |
                ACC/BIM (Autodesk Platform Services) | Proveedor tecnológico DIAN | Bancos (archivos)
 Red: VNet con endpoints privados para PostgreSQL, Key Vault y Storage (sin acceso público).
```

| Componente | Servicio recomendado | Alternativa | Notas |
|---|---|---|---|
| Backend | **Azure Container Apps** | App Service for Containers | Escala a cero en dev/qa; revisiones para despliegue azul/verde |
| Frontend | Azure Static Web Apps | Contenedor nginx (ya existe `frontend/Dockerfile`) | SPA estática + `/api` enrutado al backend |
| BD | **Azure Database for PostgreSQL Flexible Server** (General Purpose, 2–4 vCore al inicio) | — | Alta disponibilidad con zona redundante en prod; PITR 35 días |
| Secretos | Azure Key Vault + identidades administradas | — | Ningún secreto en código, imágenes ni variables de pipeline |
| Archivos | Azure Blob Storage | — | Versionado, soft delete, inmutabilidad para exportaciones de auditoría |
| Observabilidad | Application Insights + Log Analytics | — | Trazas por petición, métricas de negocio, alertas a Teams |
| Imágenes | Azure Container Registry | GitHub Container Registry | Escaneo de vulnerabilidades |
| IaC | **Bicep** (o Terraform) en el repo | — | Ambientes reproducibles; cero cambios manuales en portal |

**Región**: verificar si hay región de Azure en Colombia con los servicios requeridos; si no, usar
una región con buena latencia (p. ej. Brazil South o East US 2) y documentar la **transferencia
internacional de datos** conforme a la Ley 1581 y a las guías de la SIC (§6.2).

---

## 4. Ambientes y ciclo de entrega

| Ambiente | Propósito | Datos | Despliegue | Acceso |
|---|---|---|---|---|
| **local** | Desarrollo (humanos y agentes) | Sintéticos (`python -m app.seed`) | `scripts/dev.ps1` / `dev.sh` | Desarrolladores |
| **dev** | Integración continua | Sintéticos | Automático en cada merge a `main` | Equipo de proyecto |
| **qa / staging** | Pruebas funcionales y de aceptación (UAT), ensayos de migración | **Anonimizados** (§8.3) | Automático por *release* candidata | Equipo + usuarios clave |
| **prod** | Operación | Reales | Manual con aprobación (ambiente protegido de GitHub) | Usuarios finales según rol |

Flujo: rama corta → PR → CI (ruff, pytest, migraciones en PostgreSQL, build, imágenes, CodeQL,
escaneo de dependencias y secretos) → revisión humana (CODEOWNERS) → merge → despliegue a dev →
promoción **de la misma imagen** a qa → UAT → aprobación → prod.

- **GitHub Actions con OIDC federado** hacia Azure (sin credenciales de larga duración en GitHub).
- **Migraciones** como Container Apps Job previo al cambio de tráfico; solo migraciones
  compatibles hacia atrás (patrón *expand/contract*) para poder revertir la aplicación sin revertir el esquema.
- **Despliegue azul/verde** con revisiones de Container Apps; reversión en minutos.
- Versionado semántico y notas de versión generadas desde los PR.

---

## 5. Seguridad

### 5.1 Identidad y acceso
- **Microsoft Entra ID**: SSO, MFA obligatorio, acceso condicional (dispositivo administrado o
  red de Prodesa para roles de aprobación). Frontend con MSAL; backend valida el token (JWKS)
  y mapea **App Roles** a los roles del ERP. Bajas de personal se propagan solas al deshabilitar la cuenta.
- Principio de mínimo privilegio; cuentas de servicio = identidades administradas.
- Revisión trimestral de accesos por cada dueño de proceso.

### 5.2 Roles y segregación de funciones (SoD)
Roles de producción (ampliables por módulo): `admin_ti`, `presupuesto_elabora`,
`presupuesto_aprueba`, `director_obra`, `residente_obra`, `compras`, `contratos`, `tesoreria`,
`contabilidad`, `consulta`, `auditoria` (solo lectura con bitácora completa).

| Acción | Quién puede | Incompatible con (mismo usuario) |
|---|---|---|
| Crear/editar versión de presupuesto | presupuesto_elabora | Aprobar esa misma versión |
| Aprobar / cerrar versión | presupuesto_aprueba (gerencia técnica) | Haberla elaborado |
| Registrar compromiso (OC/contrato) | compras / contratos | Aprobar su pago |
| Registrar ejecución/avance | residente / director de obra | Aprobar el acta de ese periodo |
| Pagos (tesorería) | tesoreria | Crear terceros o compromisos |
| Administrar usuarios/roles | admin_ti | Cualquier rol transaccional |

Las reglas SoD se validan **en el backend** (no solo ocultando botones) y cada excepción queda en auditoría.

### 5.3 Protección técnica
- Estándar de referencia: **OWASP ASVS nivel 2**. Pruebas de penetración externas antes de
  salir a producción y después de cambios mayores.
- Endpoints privados para BD, Key Vault y Storage; WAF en Front Door; TLS 1.2+; cifrado en reposo (gestionado por Azure).
- CodeQL, Dependabot, escaneo de secretos y de imágenes en CI; dependencias con versión fija.
- Límites de tamaño y validación estricta en importaciones Excel (ya implementado: todo o nada).
- Registro de seguridad en Log Analytics con retención ≥ 1 año; alertas de inicio de sesión
  anómalo vía Entra ID Protection.

### 5.4 Auditoría
- Ya existe: `created_at/updated_at/created_by/updated_by` en todas las entidades y `core_audit_log`
  para eventos de negocio (aprobar, cerrar, copiar, importar, anular).
- Producción: bitácora **solo de inserción** (permisos de BD sin UPDATE/DELETE para la aplicación),
  exportación diaria a Blob con inmutabilidad (WORM), consulta para Auditoría interna y Revisoría
  fiscal, y retención alineada con la conservación de soportes contables (10 años; validar con Jurídica).

---

## 6. Protección de datos personales (Ley 1581 de 2012)

### 6.1 Qué datos personales tendrá el ERP
- ADPRO casi no tiene datos personales (proveedores suelen ser personas jurídicas).
- **Comercial/ventas, tesorería y nómina sí**: compradores de vivienda, subsidios, datos
  financieros, empleados. Son los módulos de mayor exposición.

### 6.2 Medidas
1. **Inventario y clasificación** de datos por módulo (público / interno / confidencial / restringido);
   las bases con datos personales se reflejan en la política de tratamiento de Prodesa y, si aplica,
   en el **Registro Nacional de Bases de Datos (RNBD)** de la SIC.
2. **Finalidad y autorización**: el módulo comercial registra la autorización del titular
   (fecha, versión de la política, canal) y permite atender consultas y reclamos en los plazos legales.
3. **Privacidad desde el diseño**: minimización de campos, enmascaramiento en pantallas para roles
   que no lo necesitan, cifrado adicional de campos sensibles, registro de consultas a datos personales.
4. **Transferencia/transmisión internacional**: si la nube está fuera de Colombia, revisar con
   Jurídica el cumplimiento de las reglas de la SIC sobre países con nivel adecuado de protección
   y firmar el contrato de transmisión correspondiente con el proveedor de nube.
5. **Ambientes no productivos sin datos reales** (§8.3). Los agentes de IA y los desarrolladores
   **nunca** acceden a datos personales reales.
6. **Gestión de incidentes**: procedimiento de reporte a la SIC y a los titulares cuando corresponda;
   simulacro anual.
7. Cuando aplique por actividad inmobiliaria, el módulo comercial debe soportar los controles
   de **SAGRILAFT** (debida diligencia de compradores) que defina Cumplimiento.

---

## 7. Integraciones

| Sistema | Propósito | Mecanismo propuesto | Fase |
|---|---|---|---|
| **ProdesaClass** | Catálogo maestro de la EDT (capítulo → detalle → grupo → ítem) e insumos | ProdesaClass sigue siendo el **dueño del catálogo**; sincronización por API o importación validada a `adpro_edt_nodo` con código jerárquico estable; el ERP nunca crea ítems por fuera del flujo de ProdesaClass | 1 |
| **Power BI** | Tableros gerenciales (presupuesto vs comprometido vs ejecutado, curva S, benchmark entre proyectos) | Réplica de lectura de PostgreSQL + **vistas analíticas** versionadas (esquema `bi`); nunca contra la BD transaccional primaria; opcionalmente Microsoft Fabric | 1 |
| **ACC / BIM** | Cantidades de obra desde modelos Revit | Parámetro con el código ProdesaClass en los elementos; extracción vía Autodesk Platform Services (Model Derivative / Data Exchange) a una tabla de cantidades por ítem y modelo; el presupuestador **revisa y acepta** antes de crear la versión | 2–3 |
| **Microsoft 365** | Notificaciones de aprobación, documentos | Teams (tarjetas adaptables) y SharePoint para soportes | 2 |
| **Proveedor tecnológico DIAN** | Facturación electrónica, documento soporte, nómina electrónica, eventos RADIAN | API del proveedor habilitado; el ERP genera los datos de negocio, el proveedor firma, valida y transmite | 4–5 |
| **Bancos** | Pagos y conciliación | Archivos planos/API según cada banco | 4 |
| **Sinco** (transición) | Coexistencia | Extracciones periódicas autorizadas (§8) hasta el apagado de cada proceso | 1–5 |

Regla técnica: cada integración es un **adaptador** dentro de `app/integrations/<sistema>/` con
contrato propio, reintentos, idempotencia y bitácora; los módulos de negocio no conocen detalles del sistema externo.

---

## 8. Migración de datos desde Sinco

### 8.1 Prerrequisito legal (bloqueante)
Antes de extraer o usar información almacenada en Sinco, **Jurídica revisa el contrato de
licencia y soporte**: propiedad y portabilidad de los datos de Prodesa, mecanismos de extracción
permitidos (reportes, exportaciones, acceso a BD, API), restricciones de ingeniería inversa y
obligaciones de confidencialidad. Lo que se migra son **datos propios de Prodesa**; no se copian
estructuras, pantallas, textos, reportes ni lógica propietaria del producto.

### 8.2 Proceso
1. **Inventario**: maestros (insumos, unidades, listas de precios), APU, presupuestos y versiones
   vigentes, compromisos abiertos, ejecución acumulada; terceros solo cuando lo requiera el módulo.
2. **Extracción** con el mecanismo autorizado hacia una zona de *staging* (Blob/esquema `stg`).
3. **Mapeo**: tablas de equivalencia (código origen ↔ código ProdesaClass/ERP), unidades, tipos de insumo.
4. **Transformación y validación** con reglas automáticas (unidades válidas, jerarquía EDT completa,
   precios no negativos, ítems sin APU, duplicados) y reporte de excepciones para el dueño del dato.
5. **Carga** con la misma lógica de negocio del ERP (services), nunca escribiendo tablas a mano.
6. **Conciliación**: por proyecto y capítulo, totales de presupuesto, comprometido y ejecutado
   **iguales al peso** frente al sistema de origen; diferencias explicadas y firmadas por el dueño del proceso.
7. **Ensayos**: mínimo **tres corridas completas** en qa antes del corte real; medición de tiempos.
8. **Corte**: congelamiento acordado, carga final, conciliación, aprobación y apertura.

### 8.3 Anonimización para ambientes no productivos
- qa/dev **nunca** reciben datos personales reales. Los terceros se seudonimizan
  (nombre → "Proveedor 0001 S.A.S.", identificaciones generadas con dígito de verificación válido
  pero ficticias), se eliminan datos de contacto y bancarios, y se perturban levemente los valores
  cuando sean comercialmente sensibles.
- Script de anonimización versionado y revisado; la tabla de correspondencia (si se necesita) vive
  solo en prod con acceso restringido.

---

## 9. Operación en paralelo y criterios de salida

**Modelo**: un proyecto piloto (idealmente una etapa nueva, no una obra a mitad de camino)
opera en el ERP y en Sinco al mismo tiempo durante **2–3 cierres mensuales**.

| Criterio de salida (todos deben cumplirse) | Medición |
|---|---|
| Conciliación de totales presupuesto / comprometido / ejecutado | Diferencia = $0 en cada cierre o explicada y aprobada |
| Estabilidad | 0 incidentes críticos y ≤ 2 altos abiertos durante 30 días |
| Desempeño | p95 < 1 s en consultas frecuentes; exportaciones < 30 s |
| Usuarios | ≥ 90 % de usuarios del piloto capacitados; encuesta de satisfacción ≥ 4/5 |
| Seguridad | Pentest sin hallazgos críticos/altos abiertos; revisión de accesos hecha |
| Continuidad | Restauración de backup y DR probados (RPO/RTO cumplidos) |
| Gobierno | Acta de aceptación firmada por el dueño del proceso y por TI |

Si un criterio falla, se amplía el paralelo un ciclo; **no** se apaga el proceso en Sinco.
El apagado es **por proceso** (p. ej. "presupuesto de obra"), no por sistema completo.

---

## 10. Continuidad: backups y recuperación

| Objetivo | Meta producción | Cómo |
|---|---|---|
| RPO (pérdida máxima de datos) | ≤ 15 min | PITR de PostgreSQL Flexible (retención 35 días) + backup geo-redundante |
| RTO (tiempo de recuperación) | ≤ 4 h | IaC + imágenes inmutables + runbook; alta disponibilidad con zona redundante |
| Archivos | Sin pérdida | Blob con versionado, soft delete y replicación GRS |
| Pruebas | Trimestral | Restauración real en ambiente aislado, con acta |

---

## 11. Roadmap de módulos (visión ERP)

Detalle de fechas en [ROADMAP.md](ROADMAP.md). Cada módulo se agrega como hermano de `adpro/`
(`app/modules/<modulo>/`) sobre la misma plataforma, identidad, auditoría y CI/CD.

| # | Módulo | Alcance principal | Dependencias | Normativa clave | Decisión |
|---|---|---|---|---|---|
| 1 | **ADPRO** | Presupuesto, APU, versiones, control, tablero, Excel | ProdesaClass | — | Construir (en curso) |
| 2 | **Compras** | Solicitudes, cotizaciones, órdenes de compra, recepción en obra | ADPRO (compromisos por ítem) | Documento soporte (DIAN) vía proveedor | Construir |
| 3 | **Contratos de obra** | Contratos de mano de obra/subcontratos, actas de avance, anticipos, retenciones de garantía | ADPRO (ejecución), Compras | Retenciones; seguridad social de contratistas | Construir |
| 4 | **Comercial / ventas** | Inventario de unidades, separaciones, promesas, planes de pago, subsidios y crédito, escrituración | Proyectos | Ley 1581, SAGRILAFT, normas VIS/VIP vigentes | Construir (o evaluar CRM + integración) |
| 5 | **Tesorería** | Cuentas por pagar/cobrar, programación de pagos, bancos, flujo de caja por proyecto | Compras, Contratos, Comercial | Facturación electrónica / RADIAN vía proveedor | Construir sobre proveedor DIAN |
| 6 | **Contabilidad NIIF** | Libro mayor, centros de costo por proyecto, cierres, impuestos, información exógena, costeo de inventario de obra | Todos | NIIF, Estatuto Tributario, exógena DIAN | **Evaluar comprar/integrar** vs construir |
| 7 | **Nómina** | Nómina de personal administrativo/obra, prestaciones, PILA | Contabilidad | Nómina electrónica DIAN, seguridad social | **Recomendado comprar/integrar** |

Todo lo normativo de la DIAN (facturación electrónica, documento soporte, nómina electrónica,
eventos RADIAN) se hace **a través de un proveedor tecnológico habilitado**, nunca con conexión
directa propia. Antes de cada fase, Contabilidad e Impuestos validan la normativa vigente.

---

## 12. Modelo de desarrollo: agentes de IA en paralelo + revisión humana

Este prototipo se construyó así y el modelo escala a producción:

1. **Contrato primero**: `docs/API_CONTRATO.md` y los modelos los define un arquitecto (humano +
   IA). Los agentes trabajan en paralelo contra ese contrato.
2. **Zonas de propiedad** por carpeta (ver `CLAUDE.md`): cada agente edita solo su zona; los
   cambios en modelos o contratos se piden, no se hacen. Esto evita conflictos y mantiene el diseño.
3. **Puertas de calidad automáticas**: ruff, pytest (cada regla de negocio con prueba),
   migraciones en PostgreSQL, build, escaneos de seguridad. Nada entra sin CI verde.
4. **Revisión humana obligatoria**: todo PR lo aprueba al menos un desarrollador del equipo
   (CODEOWNERS); los cambios en seguridad, cálculos o datos los revisa además el líder técnico.
   Los dueños de proceso validan el comportamiento en qa (UAT).
5. **Guardas de datos**: los agentes solo ven datos sintéticos o anonimizados, nunca credenciales
   ni secretos de producción; no tienen permisos de despliegue a prod.
6. **Trazabilidad**: cada PR indica qué generó la IA y qué revisó la persona; decisiones en ADR.
7. **Métricas**: tiempo de entrega por historia, defectos escapados a prod, cobertura, tasa de
   reversión. Se revisan mensualmente para ajustar el balance IA/humano.

Beneficio esperado: un equipo de 2–4 personas con agentes rinde como un equipo tradicional más
grande. Riesgo: código plausible pero incorrecto. Mitigación: pruebas de negocio escritas a partir
de casos reales anonimizados validados por Presupuestos, y revisión humana.

---

## 13. Gobierno

| Instancia | Integrantes | Frecuencia | Decide |
|---|---|---|---|
| **Comité directivo** | Sponsor (Gerencia General o Financiera), Director técnico, Director financiero, líder de TI | Mensual | Alcance por fase, presupuesto, go/no-go de cada salida a producción |
| **Comité de producto** | Dueños de proceso, líder técnico, product owner | Quincenal | Prioridades del backlog, aceptación funcional |
| **Comité de cambios** | Líder técnico, TI/Seguridad, dueño del proceso afectado | Por *release* | Pase a producción, ventanas de mantenimiento |

- **Dueños de proceso**: Presupuestos (ADPRO), Compras, Contratos, Comercial, Tesorería,
  Contabilidad. Cada uno firma criterios de aceptación y conciliaciones de su módulo.
- **Product owner** interno (dedicación ≥ 50 %) con conocimiento de presupuesto y obra.
- Matriz RACI por módulo y política de cambios documentada antes del piloto.

---

## 14. Equipo, tiempos y costos estimados

### 14.1 Supuestos
- Costos mensuales **totales para la empresa** (salario + prestaciones, o tarifa de contratista) en
  COP de 2026, rangos de mercado para Bogotá; deben validarse con Gestión Humana/Compras.
- TRM de referencia: COP 4.000 por USD (los costos de nube y licencias varían con la TRM).
- Desarrollo asistido por IA (§12); sin él, los tiempos crecen entre 30 % y 60 %.
- No incluye: tiempo de usuarios clave internos, licencias de Power BI/M365 ya existentes, ni el
  costo actual de Sinco (que Finanzas debe aportar para el caso de negocio).

| Rol | Costo mensual (COP) | Dedicación |
|---|---|---|
| Líder técnico / arquitecto | 18 – 26 M | 100 % |
| Desarrollador full-stack senior | 12 – 18 M | 100 % (1–3 personas según fase) |
| QA / analista funcional | 8 – 12 M | 50 – 100 % |
| DevOps / seguridad en la nube | 14 – 20 M | 25 – 50 % |
| Herramientas de IA para desarrollo | 0,4 – 1,0 M por persona | — |

### 14.2 Por fase

| Fase | Duración | Equipo | Personas (COP) | Nube y servicios (COP) | Otros (COP) | **Total (COP)** |
|---|---|---|---|---|---|---|
| 0. Prototipo y decisión | 1 – 2 meses | Actual (1 persona + IA) | — (interno) | ≈ 0 | — | **Interno** |
| 1. Piloto ADPRO | 5 – 6 meses | Líder + 2 devs + QA 50 % + DevOps 50 % | 265 – 470 M | 12 – 30 M | Pentest 25 – 60 M | **≈ 300 – 560 M** |
| 2. Producción ADPRO | 3 meses | Líder + 1–2 devs + QA 50 % + DevOps 25 % | 115 – 220 M | 15 – 30 M | Capacitación 10 – 25 M | **≈ 140 – 275 M** |
| 3. Compras + Contratos | 6 – 8 meses | Líder + 2–3 devs + QA | 300 – 740 M | 30 – 60 M | Proveedor DIAN (documento soporte) según volumen | **≈ 330 – 800 M** |
| 4. Comercial + Tesorería | 8 – 10 meses | Líder + 3 devs + QA + analista | 560 – 1.040 M | 40 – 80 M | Pentest, proveedor DIAN | **≈ 600 – 1.120 M** |
| 5. Contabilidad NIIF / Nómina | 6 – 12 meses | Según decisión comprar/construir | 300 – 900 M (si se construye) | 40 – 90 M | Licencias si se compra | **Decidir en Fase 4** |

- **Nube en producción (ADPRO)**: ≈ USD 800 – 2.000/mes (≈ COP 3 – 8 M/mes) incluyendo
  PostgreSQL con alta disponibilidad, Container Apps, Front Door/WAF, monitoreo y backups.
  dev + qa: ≈ USD 250 – 600/mes adicionales.
- Cálculo: suma de costos mensuales del equipo × duración (p. ej. Fase 1: 53 – 78 M/mes × 5 – 6 meses).
- **Contingencia** recomendada: 15 – 20 % sobre cada fase (no incluida en los totales).
- Primer compromiso real que se pide a la Dirección: **solo la Fase 1** (piloto), con
  go/no-go antes de la Fase 2.

---

## 15. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| 1 | Restricciones contractuales de Sinco sobre extracción/uso de datos | Media | Alto | Revisión jurídica previa (§8.1); usar solo mecanismos autorizados; solo datos propios |
| 2 | Alcance creciente ("ya que estamos…") | Alta | Alto | Fases con alcance cerrado, comité de producto, backlog priorizado; lo nuevo va a la siguiente fase |
| 3 | Dependencia de pocas personas (*bus factor*) | Alta | Alto | Documentación viva (CLAUDE.md, ADR, contrato), revisión cruzada, mínimo 2 personas por módulo, código en GitHub de Prodesa |
| 4 | Errores en cálculos (presupuesto, AIU, explosión) | Media | Alto | Fórmulas únicas en `calculos.py` con pruebas; conciliación al peso en el piloto; casos reales anonimizados como pruebas |
| 5 | Baja adopción por usuarios acostumbrados al sistema actual | Media | Alto | Usuarios clave desde el diseño, capacitación, importación/exportación Excel, paralelo |
| 6 | Incumplimiento normativo (DIAN, Ley 1581) | Baja | Muy alto | Proveedor tecnológico habilitado; validación de Contabilidad/Jurídica por fase; privacidad desde el diseño |
| 7 | Incidente de seguridad o fuga de datos | Baja | Muy alto | Entra ID + MFA, endpoints privados, Key Vault, pentest, monitoreo, datos no productivos anonimizados |
| 8 | Calidad de código generado por IA | Media | Medio | Revisión humana obligatoria, CI estricto, pruebas de negocio, métricas de defectos |
| 9 | Costos de nube por encima de lo previsto | Baja | Medio | Presupuestos y alertas de costo en Azure, escalado a cero en dev/qa, revisión mensual |
| 10 | Construir módulos commodity (contabilidad/nómina) con alto costo y riesgo | Media | Alto | Análisis comprar vs construir en Fase 4; integrar productos certificados cuando convenga |
| 11 | Calidad de datos maestros heredados | Alta | Medio | Reglas de validación, reportes de excepciones, depuración con dueños de dato antes del corte |

---

## 16. Próximos pasos (30 días)

1. Presentar el prototipo y la [propuesta ejecutiva](PROPUESTA_DIRECTIVOS.md) a la Dirección.
2. Designar sponsor, product owner y dueño del proceso de Presupuestos.
3. Solicitar a Jurídica la revisión del contrato de Sinco (§8.1) y a Finanzas el costo anual
   actual de licencias, soporte y personalizaciones para el caso de negocio.
4. Con TI: registrar la aplicación en Entra ID (ambiente dev), crear suscripción/grupos de recursos
   de Azure y repositorio en la organización de GitHub de Prodesa con ramas protegidas.
5. Elegir el proyecto piloto y la fecha objetivo del primer cierre en paralelo.
