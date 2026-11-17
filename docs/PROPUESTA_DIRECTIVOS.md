# Propuesta a la Dirección — ERP propio de Prodesa, empezando por ADPRO

> Documento ejecutivo (lectura de 5 minutos). El detalle técnico, de costos y de riesgos está en
> [ESTRATEGIA_PRODUCCION.md](ESTRATEGIA_PRODUCCION.md) y las fases en [ROADMAP.md](ROADMAP.md).
> Cifras en COP de 2026, **rangos indicativos** con supuestos explícitos; no son cotizaciones.

## 1. El problema

- El presupuesto y el control de obra son el corazón del negocio de Prodesa (márgenes VIS/No VIS
  estrechos, alta sensibilidad al precio del acero, el concreto y la mano de obra), pero hoy
  dependen de un ERP genérico de terceros, de archivos Excel paralelos y de conciliaciones manuales.
- Las comparaciones entre versiones (BASE, FIC, FIV, CONTROL), la explosión de insumos y el
  tablero presupuesto vs. comprometido vs. ejecutado exigen horas de trabajo manual y llegan tarde
  a las decisiones de obra.
- Cada mejora del proceso depende del roadmap y de los costos de personalización del proveedor.
- Los datos no fluyen de forma natural hacia ProdesaClass, Power BI ni los modelos BIM (ACC).

## 2. La propuesta

Construir **gradualmente** un ERP propio, **módulo por módulo**, empezando por **ADPRO**
(presupuesto y control de obra), que es lo que diferencia a Prodesa. Lo regulado y estandarizado
(facturación y nómina electrónica, contabilidad) se **integra o compra** a proveedores habilitados.

El **prototipo ya funciona** (hoy, en local, con datos 100 % ficticios):

| Capacidad | Estado del prototipo |
|---|---|
| Maestros: insumos, listas de precios con vigencia por ciudad, proyectos, EDT estilo ProdesaClass | Listo |
| APU por ítem con desperdicio y precio vigente a una fecha | Listo |
| Presupuesto con versiones (BASE, FIC, FIV, CONTROL), aprobación inmutable, AIU e IVA sobre utilidad | Listo |
| Explosión de insumos, comparativo entre versiones (diferencia unitaria e impacto) | Listo |
| Compromisos, ejecución mensual y tablero presupuesto / comprometido / ejecutado / saldo | Listo |
| Importación y exportación a Excel, auditoría de cambios, roles de usuario | Listo |

Se construyó con **desarrollo asistido por agentes de IA y revisión humana**, lo que permite un
equipo pequeño con calidad controlada (pruebas automáticas en cada cambio).

## 3. Beneficios esperados

1. **Decisiones más rápidas**: comparativo FIC vs. FIV y tablero de control en minutos, no días.
2. **Una sola verdad del presupuesto**: versiones aprobadas inmutables, trazabilidad de quién
   cambió qué y cuándo.
3. **Proceso propio**: el sistema se adapta a la metodología de Prodesa (ProdesaClass, EDT, AIU),
   no al revés; mejoras sin depender de terceros.
4. **Integración nativa** con Microsoft 365 (inicio de sesión corporativo), Power BI, ProdesaClass
   y BIM/ACC.
5. **Reducción progresiva** de licencias, personalizaciones y Excel paralelos (cuantificar con el
   costo actual que aporte Finanzas).

## 4. Fases

| Fase | Duración | Resultado | Inversión aprox. (COP) |
|---|---|---|---|
| 0. Prototipo y decisión | 1 – 2 meses | Prototipo funcional (este) y caso de negocio | Interna |
| **1. Piloto ADPRO** | 5 – 6 meses | ADPRO en Azure con inicio de sesión corporativo, un proyecto piloto en **paralelo** con el sistema actual | **≈ 300 – 560 M** |
| 2. Producción ADPRO | 3 meses | ADPRO para todos los proyectos; apagado del proceso de presupuesto en el sistema actual si se cumplen criterios | ≈ 140 – 275 M |
| 3. Compras + Contratos | 6 – 8 meses | Órdenes y contratos contra el presupuesto | ≈ 330 – 800 M |
| 4. Comercial + Tesorería | 8 – 10 meses | Ventas de unidades, cartera, pagos y flujo de caja | ≈ 600 – 1.120 M |
| 5. Contabilidad / Nómina | Por definir | Decisión comprar o construir en la Fase 4 | Por definir |

Nube en producción para ADPRO: ≈ COP 3 – 8 M/mes. Contingencia sugerida: 15 – 20 % por fase.
Supuestos: equipo de 3 – 5 personas con herramientas de IA, tarifas de mercado de Bogotá,
TRM 4.000; no incluye el tiempo de usuarios clave internos.

## 5. Riesgos principales y cómo se controlan

| Riesgo | Control |
|---|---|
| Restricciones del contrato con el proveedor actual sobre el uso o la extracción de datos | **Revisión jurídica de la licencia antes de extraer cualquier dato**; solo datos propios de Prodesa |
| Errores en los cálculos | Fórmulas únicas probadas automáticamente; conciliación al peso durante el paralelo |
| Alcance que crece sin control | Fases cerradas, comité de producto, go/no-go por fase |
| Dependencia de pocas personas | Documentación viva, código en el GitHub de Prodesa, revisión cruzada |
| Seguridad y datos personales (Ley 1581) | Inicio de sesión corporativo con MFA, cifrado, auditoría, datos anonimizados fuera de producción |
| Obligaciones DIAN | Siempre a través de un proveedor tecnológico habilitado |

El sistema actual **sigue siendo el oficial** de cada proceso hasta que el módulo propio cumpla
criterios de salida medibles (conciliación en $0, estabilidad, seguridad y aceptación del dueño
del proceso durante 2 – 3 cierres mensuales).

## 6. Decisión que se solicita

1. **Aprobar la Fase 1 (Piloto ADPRO)** por ≈ COP 300 – 560 M más contingencia, con revisión
   go/no-go al terminar antes de comprometer la Fase 2.
2. **Designar** un sponsor directivo, un product owner (≥ 50 % de dedicación) y al dueño del
   proceso de Presupuestos.
3. **Autorizar** a Jurídica la revisión del contrato de licencia del sistema actual y a Finanzas
   el levantamiento de su costo anual total, para cerrar el caso de negocio.
4. **Elegir** el proyecto piloto (idealmente una etapa nueva).
