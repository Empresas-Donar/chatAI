# Spec: /reportes incluye todos los reportes de contratistas en el orden del menú

## Qué

La página `/reportes` debe incluir **todos** los reportes del módulo Contratistas en el mismo orden
que aparecen en el menú lateral, y los PDFs generados desde `/reportes` deben ser idénticos a los
PDFs descargados desde cada sección individual (una sola implementación de generación de PDF).

## Criterios de aceptación

- [ ] La página `/reportes` muestra los 9 reportes de contratistas: Detalle operacional, Por persona operacional, General operacional, Resumen por persona, Horas extra por persona, Jornadas por trabajador, Detalle tractorista, General tractorista, Resumen tractorista
- [ ] El orden en `/reportes` es idéntico al orden del menú lateral de navegación
- [ ] El PDF de cada reporte generado desde `/reportes` es idéntico al PDF de la sección individual
- [ ] Una sola implementación de generación de HTML por reporte, reutilizada en ambos lugares

## Contexto

### Problema 1 — Reporte faltante: "Jornadas por trabajador"

El reporte `jornadas-trabajador` fue agregado al menú en el issue #20 pero **no** fue agregado a `AVAILABLE_REPORTS` ni a `_REPORT_GENERATORS` en `reports_controller.py`.

### Problema 2 — Orden incorrecto

El menú define este orden para Contratistas:
1. Detalle operacional (`detalle`)
2. Por persona operacional (`contratista`)
3. General operacional (`general`)
4. Resumen por persona (`resumen-persona`)
5. Horas extra por persona (`resumen-horas`)
6. Jornadas por trabajador (`jornadas-trabajador`)

Mientras que `AVAILABLE_REPORTS` tiene:
1. General operacional
2. Detalle operacional
3. Por persona operacional
4. Resumen por persona
5. Horas extra por persona

(Diferente orden, y falta `jornadas-trabajador`)

### Problema 3 — Dos implementaciones de PDF distintas

Los endpoints individuales (e.g. `/api/tarjas/general/download-pdf`) en `tarjas_controller.py` usan SQL y HTML distintos a los `_html_*` en `reports_controller.py`:

- La función `_html_detalle` en `reports_controller.py` usa `appsheet.tarjas_reporte` con columnas distintas a las que usa `download_tarjas_detalle_pdf` en `tarjas_controller.py`
- `_html_contratista` produce una tabla diferente a `download_tarjas_contratista_pdf`
- `_html_resumen_persona` produce un pivot de fechas; `download_tarjas_resumen_persona_pdf` produce un listado flat
- `jornadas-trabajador` no existe en `reports_controller.py`

**Solución:** Mover la lógica HTML de cada reporte a `reports_controller.py` como funciones `_html_*` canónicas y hacer que los endpoints individuales en `tarjas_controller.py` llamen a esas mismas funciones.

### Archivos involucrados

- `chatai/backend/controllers/reports_controller.py` — añadir `jornadas-trabajador`, corregir orden, unificar HTML
- `chatai/backend/controllers/tarjas_controller.py` — hacer que download-pdf endpoints deleguen a `reports_controller`

## Decisiones

- **Fuente canónica en `reports_controller.py`**: Las funciones `_html_*` ya existentes en `reports_controller.py` son la fuente de verdad. Los endpoints individuales en `tarjas_controller.py` ahora delegan a ellas con `import controllers.reports_controller as _rc`.
- **Sin cambio al SQL de tractoristas `_html_*`**: Las funciones `_html_detalle_tractorista`, `_html_general_tractorista` y `_html_resumen_tractorista` ya existían y no se alteraron — solo se agregó el endpoint de descarga PDF para `resumen-persona-tractorista` que faltaba.
- **CSS `.total-row`**: Se agregó a `_PDF_CSS` en `reports_controller.py` para que la fila de total de `_html_jornadas_trabajador` quede con el mismo fondo azul claro que la versión individual.
- **Parámetros adicionales descartados**: Los endpoints individuales aceptan filtros extras (centro_costo, labor, tipo_pago, trabajador) que la vista `/reportes` no expone. Al delegar, solo se pasan `empresa` y `contratista` — igual que en el bulk PDF. Esto es correcto ya que `/reportes` es un reporte general no filtrado por labor.

## Implementado

- `chatai/backend/controllers/reports_controller.py` — corregido orden en `AVAILABLE_REPORTS`, agregado `jornadas-trabajador`, nueva función `_html_jornadas_trabajador`, `jornadas-trabajador` en `_REPORT_GENERATORS`, CSS `.total-row` en `_PDF_CSS`
- `chatai/backend/controllers/tarjas_controller.py` — import de `_rc`, delegación en: `download_tarjas_general_pdf`, `download_tarjas_detalle_pdf`, `download_tarjas_contratista_pdf`, `download_tarjas_resumen_persona_pdf`, `download_tarjas_resumen_horas_pdf`, `download_tarjas_jornadas_trabajador_pdf`; nuevo endpoint `download_tarjas_resumen_persona_tractorista_pdf`
- `chatai/tests/test_22_reportes_orden_completo.py` — 14 tests: completitud, orden del menú y delegación de PDF

## Tests

14 passed, 0 failed · isolation: N/A (no tenant scoping involved — static analysis tests)

## QA Manual

1. Abrir `/reportes` y verificar que aparecen los 9 reportes: "Detalle operacional", "Por persona operacional", "General operacional", "Resumen por persona", "Horas extra por persona", "Jornadas por trabajador", "Detalle tractorista", "General tractorista", "Resumen tractorista"
2. Confirmar que el orden visual en la sección Contratistas es: Detalle → Por persona → General → Resumen por persona → Horas extra → Jornadas por trabajador (igual que el menú lateral)
3. Seleccionar el reporte "Jornadas por trabajador" en `/reportes`, elegir un rango de fechas con datos conocidos y descargar el PDF; comparar visualmente con el PDF descargado desde la página individual `/tarjas/jornadas-trabajador` con los mismos filtros — deben ser idénticos en estructura y datos

