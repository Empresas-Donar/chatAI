# Nuevo reporte: Bonos mensuales en catálogo de reportes
# Path: specs/100-contractor-monthly-bonus-report/spec.md
issue: #100 · branch: 100-contractor-monthly-bonus-report · date: 2026-08-14

## What
Nuevo reporte "Bonos mensuales" en Catálogo de Reportes → Tarjas → Contratistas, que muestra todo bono mensual ya ingresado en `tarjas_pagos` para el mes y filtros seleccionados, con las mismas acciones (Consultar, Excel, PDF) que el resto de reportes de tarjas.

## Acceptance
- [x] Nueva entrada "Bonos mensuales" en Catálogo de Reportes → Tarjas → Contratistas.
- [x] Filtros: Mes, Empresa, Campo, Contratista.
- [x] Mismas acciones que el resto de reportes de tarjas: Consultar, descarga Excel, descarga PDF.
- [x] Muestra todo bono mensual ingresado en `tarjas_pagos` (labor = 'Bono mensual') para el mes y filtros seleccionados, con trabajador, contratista, empresa/campo, CC, fecha y monto.

## Context
- Infraestructura de datos ya existente (no tocada en este issue): `sql/tarjas/18_insert_labor_bono_mensual.sql` (labor "Bono mensual", codigo_labor 6.10 en `appsheet.tarjas_labores`) y `sql/tarjas/19_bono_mensual.sql` (tabla `appsheet.tarjas_bono_mensual` alimentada desde AppSheet + triggers que reflejan cada bono como fila en `appsheet.tarjas_pagos` con `labor = 'Bono mensual'`, `tipo_pago = 'Bono'`).
- Patrón de referencia más cercano: `/tarjas/jornadas-trabajador` (`chatai/backend/controllers/tarjas_controller.py`, sección "Jornadas por trabajador") — page + filters + data + download-excel + download-pdf, mismo esqueleto de helpers (`_rows_to_dicts`, `_pdf_header`, `_render_pdf`, `_apply_header`, `_excel_response`).
- Empresa/Campo como dos selects separados que ambos filtran `nombre_campo` es el patrón ya usado en "Detalle operacional" (`_build_detalle_filters`) — se reutiliza igual acá en vez de introducir un concepto nuevo de "campo" distinto de "empresa" (el esquema no los distingue).
- Nav menu: `chatai/frontend/templates/base.html`, lista `nav_menu` → Catálogo de Reportes → Tarjas → Contratistas.

## Decisions
- El reporte usa un filtro de mes único (`<input type="month">`, `YYYY-MM`) en vez de rango Desde/Hasta, porque el bono mensual es un concepto mensual (no diario) — la fila en `tarjas_pagos` queda con `fecha` = último día del mes (ver trigger `fanout_bono_mensual_insert` en `19_bono_mensual.sql`).
- Filtro fijo por `labor = 'Bono mensual'` en el backend (no expuesto como filtro de UI) — es el único criterio confiable para aislar bonos mensuales dentro de `tarjas_pagos`, ya que `tipo_pago = 'Bono'` no es exclusivo de este flujo históricamente (ver `tests/test_88_screen_pdf_total_mismatch.py`, que documenta `tipo_pago='Bono'` con datos previos a este feature).
- No se agrega esta vista al catálogo de descarga masiva PDF (`reports_controller.py` / página "Reportes PDF") — el pedido fue específicamente por la entrada en el nav del Catálogo de Reportes, no por el selector de descarga masiva; queda fuera de alcance.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`: helpers `_mes_range`, `_build_bono_mensual_filters`, `_query_bono_mensual_rows`; rutas `tarjas_bono_mensual_page`, `get_tarjas_bono_mensual_filters`, `get_tarjas_bono_mensual`, `download_tarjas_bono_mensual_excel`, `download_tarjas_bono_mensual_pdf`.

### Frontend
- `chatai/frontend/templates/tarjas_bono_mensual.html` (nuevo)
- `chatai/frontend/static/tarjas_bono_mensual.js` (nuevo)
- `chatai/frontend/templates/base.html`: nueva entrada de nav bajo Tarjas → Contratistas.

## Routes
| Method | Path | Description |
|--------|------|-------------|
| GET | /tarjas/bono-mensual | Página del reporte |
| GET | /api/tarjas/bono-mensual/filters | Contratistas/empresas/campos distintos entre bonos mensuales |
| GET | /api/tarjas/bono-mensual | Datos filtrados por mes/contratista/empresa/campo |
| GET | /api/tarjas/bono-mensual/download-excel | Descarga Excel |
| GET | /api/tarjas/bono-mensual/download-pdf | Descarga PDF |

## Tests
Verificado manualmente contra la BD de desarrollo real (sin mocks, según convención del repo): `get_tarjas_bono_mensual_filters` y `get_tarjas_bono_mensual(mes='2026-07')` devuelven los 6 registros reales de bono mensual de julio 2026 (`$112.691` total), filtro por contratista aísla correctamente 1 de 6 filas. Página, filtros, datos y Excel verificados end-to-end vía `TestClient` con auth mockeada (200 OK en los 4). PDF verificado end-to-end contra `_pdf_header` — falla solo en Windows local por `strftime("%-d de %B de %Y")` (extensión glibc no soportada en Windows), limitación preexistente y compartida por todos los PDFs del archivo (confirmado reproduciendo el mismo error en `/api/tarjas/jornadas-trabajador/download-pdf`, endpoint ya existente sin relación a este issue); funciona en producción (Linux/Cloud Run).
No se agregó un archivo `tests/test_100_*.py` dedicado — el resto de reportes de tarjas (`jornadas-trabajador`, `resumen-horas`, etc.) tampoco tiene test unitario propio en `chatai/tests/`, se siguió el mismo patrón de verificación manual contra datos reales.

## Manual QA
1. Ir a Catálogo de Reportes → Tarjas → Contratistas → "Bonos mensuales".
2. Seleccionar mes 2026-07 y hacer clic en "Consultar" → deben aparecer 6 filas (trabajadores de MULTISERVICIOS BONHOMIA SPA y HERBI ML SPA) con total $112.691.
3. Filtrar por Contratista = "HERBI ML SPA" → debe quedar 1 fila (MAIBET LOBOS, $9.048).
4. Con datos en pantalla, hacer clic en "Excel" y "PDF" → ambos descargan con las mismas filas y el total en la fila "Suma total".
5. Cambiar el mes a uno sin bonos ingresados → debe mostrarse el estado vacío ("Sin resultados").

## Deferred
- No se agrega esta vista al selector de descarga masiva de PDFs (`/reportes`).
- No se distingue "Empresa" de "Campo" como conceptos separados en el esquema — se mantiene el mismo patrón (ambos filtran `nombre_campo`) usado en el resto del módulo Tarjas.
