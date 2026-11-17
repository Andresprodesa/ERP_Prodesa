# Roadmap — ERP Prodesa

> Fases del ERP propio, de prototipo a producción y de ADPRO al resto de módulos.
> Costos, supuestos y riesgos: [ESTRATEGIA_PRODUCCION.md](ESTRATEGIA_PRODUCCION.md) §14–15.
> Resumen para la Dirección: [PROPUESTA_DIRECTIVOS.md](PROPUESTA_DIRECTIVOS.md).
> Duraciones indicativas; cada fase cierra con un **go/no-go** del comité directivo.

## Vista general

| Fase | Duración | Entregable principal | Puerta de salida |
|---|---|---|---|
| 0. Prototipo y decisión | 1 – 2 meses | Prototipo local ADPRO con datos sintéticos, estrategia y caso de negocio | Aprobación de la Fase 1 |
| 1. Piloto ADPRO | 5 – 6 meses | ADPRO en Azure (dev/qa/prod) con Entra ID, un proyecto piloto en paralelo con Sinco | Criterios de salida del paralelo (§9 de la estrategia) |
| 2. Producción ADPRO | 3 meses | ADPRO para todos los proyectos activos; apagado del proceso de presupuesto en Sinco | Acta de aceptación del dueño de proceso |
| 3. Compras + Contratos | 6 – 8 meses | Solicitudes, órdenes de compra, contratos de obra y actas contra el presupuesto | Paralelo de 2 cierres con conciliación |
| 4. Comercial + Tesorería | 8 – 10 meses | Ventas de unidades, cartera, pagos, flujo de caja por proyecto | Paralelo + validación de Tesorería y Jurídica |
| 5. Contabilidad NIIF / Nómina | Por definir | Integración con producto certificado o desarrollo propio | Decisión comprar/construir tomada en Fase 4 |

## Fase 0 — Prototipo y decisión (en curso)

- [x] Fundación: monolito modular FastAPI + React, auth JWT con roles, auditoría, migraciones.
- [x] ADPRO: maestros, APU, presupuesto versionado (BASE/FIC/FIV/CONTROL), AIU, explosión,
      comparativo, compromisos, ejecución, tablero, Excel.
- [x] Datos 100 % sintéticos (`python -m app.seed`): 2 proyectos demo, 8 capítulos, ~40 ítems
      con APU, versión BASE aprobada y CONTROL en borrador, compromisos y 3 meses de ejecución.
- [x] DevOps local: `scripts/dev.ps1` / `scripts/dev.sh`, docker-compose (PostgreSQL + backend +
      frontend), CI en GitHub Actions (ruff, pytest, migraciones en PostgreSQL, build).
- [ ] Presentación a la Dirección y decisión sobre la Fase 1.
- [ ] Revisión jurídica de la licencia de Sinco (bloqueante para usar cualquier dato extraído).

## Fase 1 — Piloto ADPRO

1. **Plataforma**: suscripción y grupos de recursos Azure; infraestructura como código; Container
   Apps, PostgreSQL Flexible, Key Vault, Blob, Application Insights; ambientes dev/qa/prod.
2. **Identidad**: Entra ID (SSO + MFA) con App Roles equivalentes a admin/presupuesto/obra/consulta;
   matriz de segregación de funciones.
3. **Producto**: mejoras priorizadas con Presupuestos (p. ej. sub-APU, aprobaciones en dos
   niveles, flujo FIC → FIV, reportes para comité de obra); integración de lectura con ProdesaClass.
4. **Datos**: carga inicial de maestros y del presupuesto del proyecto piloto (solo datos propios,
   tras visto bueno jurídico), con conciliación al peso; anonimización para dev/qa.
5. **Calidad y seguridad**: pruebas de negocio con casos reales anonimizados, pentest, backups y
   restauración probados.
6. **Paralelo**: 2 – 3 cierres mensuales del proyecto piloto en ERP y Sinco.

## Fase 2 — Producción ADPRO

- Despliegue a todos los proyectos activos por oleadas (regional/ciudad).
- Capacitación, mesa de ayuda y manuales; modelo semántico para Power BI.
- Apagado **por proceso** del presupuesto de obra en Sinco al cumplir criterios.
- Integración con ACC/BIM para cantidades (lectura de modelos, trazabilidad ítem ↔ elemento).

## Fase 3 — Compras + Contratos

- Solicitudes de material desde obra, cotizaciones, órdenes de compra, recepción.
- Contratos de mano de obra y subcontratos, actas de avance, anticipos, retenciones de garantía.
- Compromisos y ejecución de ADPRO alimentados automáticamente desde estos módulos.
- Documento soporte electrónico vía proveedor tecnológico habilitado por la DIAN.

## Fase 4 — Comercial + Tesorería

- Inventario de unidades, separaciones, promesas, planes de pago, subsidios y crédito, escrituración.
- Cuentas por pagar/cobrar, programación de pagos, bancos, flujo de caja por proyecto.
- Facturación electrónica y eventos RADIAN vía proveedor habilitado; Ley 1581 y SAGRILAFT.
- Análisis comprar vs. construir para contabilidad NIIF y nómina.

## Fase 5 — Contabilidad NIIF / Nómina

- Según la decisión de la Fase 4: integración con producto certificado (recomendado para nómina)
  o desarrollo propio sobre la misma plataforma.
- Centros de costo por proyecto alimentados desde ADPRO, Compras, Contratos y Tesorería.

## Mejoras técnicas identificadas (backlog)

- Sub-APU (APU que contiene otros APU) — fuera del alcance v1 por diseño.
- Aprobaciones multinivel y firmas en cambios de versión.
- Exportación inmutable del `audit_log` (WORM) y consultas para Revisoría Fiscal.
- Multimoneda/indexación de precios (IPC, ICCV) para proyecciones.
- Escaneos de seguridad en CI (dependencias, SAST, imágenes) y despliegue continuo por ambiente.
- Verificar en PostgreSQL administrado (Azure) que `pg_trgm` esté habilitada; si no, la
  migración 0002 omite los índices de búsqueda (deja un NOTICE) y el filtro `q` funciona sin índice.
- Ajuste de redondeo opcional en la explosión de insumos para que `total_insumos` cuadre al peso
  con el costo directo (hoy puede diferir unos pesos por redondear cada línea × insumo).
- Unificar `control._nodos_y_capitulos` con `presupuesto.capitulos_de_items` (hoy ambos resuelven
  el capítulo de cada ítem; el de control también devuelve los nodos).
- `npm audit` de dependencias de desarrollo (vite/esbuild) antes de producción.
