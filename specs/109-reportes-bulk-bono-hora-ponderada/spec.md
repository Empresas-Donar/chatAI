# Agregar Bonos Mensuales y Hora Ponderada 9h a Descarga de Reportes PDF
# Path: specs/109-reportes-bulk-bono-hora-ponderada/spec.md
issue: #109 · branch: 109-reportes-bulk-bono-hora-ponderada · date: 2026-08-14

## What
La página "Descarga de Reportes" (`/reportes`, PDF masivo/combinado) ahora incluye los dos reportes nuevos de Tarjas — Contratistas que faltaban en la lista de selección: **Bonos mensuales** (issue #100) y **Hora ponderada 9h** (issue #102).

## Acceptance
- [x] "Bonos mensuales" aparece en la categoría "Tarjas — Contratistas" de `/reportes` y se puede descargar solo o combinado con otros reportes
- [x] "Hora ponderada 9h" aparece en la misma categoría y se puede descargar solo o combinado con otros reportes
- [x] Ambos usan el mismo rango de fechas / filtros de empresa y contratista que ya aplica la página a todos los demás reportes

## Context
- `reports_controller.py` mantiene su propio registro `AVAILABLE_REPORTS` (metadata para las tarjetas de selección) y `_REPORT_GENERATORS` (dict id → función que arma una sección de HTML). Cada función recibe `(cur, fecha_inicio, fecha_termino, empresa, contratista=None)` — el mismo rango/filtros que ya usa la página para los 9 reportes existentes.
- Por convención ya establecida en este archivo, `reports_controller.py` **no** importa nada de `tarjas_controller.py` — duplica sus propios helpers de PDF (`_pdf_header`, `_fmt_clp`, `_fmt_date_display`, `_PDF_CSS`). Se siguió el mismo patrón: `_hora_ponderada_9h()` se duplicó localmente (función pura de una línea, mismo comportamiento que la versión de `tarjas_controller.py`) en vez de importarla cruzando controllers.
- **Bonos mensuales**, en su página propia (`/tarjas/bono-mensual`), filtra por un mes calendario completo (`mes=YYYY-MM`). En el PDF masivo no existe ese selector — se usa directamente el rango `fecha_inicio`/`fecha_termino` que ya trae la página, filtrando `labor = 'Bono mensual'` sobre ese rango (sin forzar "mes completo").
- **Hora ponderada 9h** ya usaba `fecha_inicio`/`fecha_termino` en su página propia, así que se tradujo directo: mismo pivot Labor × CC con una columna por fecha, mismo cálculo `hora_ponderada_9h = ROUND(total_trabajado / horas_trabajadas * 9, 0)`, fila final con la tasa ponderada global (blend, no suma de filas).
- Ninguna de las dos usa filtros propios adicionales (Bonos mensuales tiene "Campo"; Hora ponderada tiene "CC"/"Labor") — igual que el resto de los reportes ya registrados en este archivo, que tampoco exponen sus filtros extra en la versión masiva.
- Reutilizan las clases CSS ya existentes en `_PDF_CSS` de `reports_controller.py` (`.total-row`, `.pivot-table`/`.col-worker`/`.col-tipo`/`.col-total`, `tr.worker-first`) — no se agregó CSS nuevo.

## Implemented
### Backend
- `chatai/backend/controllers/reports_controller.py`:
  - `AVAILABLE_REPORTS` — 2 entradas nuevas (`bono-mensual`, `hora-ponderada-9h`), categoría "Tarjas — Contratistas"
  - `_html_bono_mensual()` — nueva función generadora
  - `_hora_ponderada_9h()` — helper puro duplicado de `tarjas_controller.py`
  - `_html_hora_ponderada()` — nueva función generadora
  - `_REPORT_GENERATORS` — 2 entradas nuevas mapeando a las funciones anteriores

### Tests
- `chatai/tests/test_109_reportes_bulk_bono_hora_ponderada.py` — 8 tests contra la base de datos real: registro en `AVAILABLE_REPORTS`/`_REPORT_GENERATORS`, HTML de cada generador (incluye validación de que Bonos Mensuales usa el rango de fechas y no un mes fijo), y 3 tests de integración contra `bulk_pdf_download()` (cada reporte nuevo solo, y los dos combinados junto con un reporte preexistente).

## Routes
Sin rutas nuevas — mismos endpoints `/reportes` y `/api/reportes/bulk-pdf`, ahora aceptan `bono-mensual` y `hora-ponderada-9h` como valores de `reports`.

## Tests
```
pytest tests/test_109_reportes_bulk_bono_hora_ponderada.py -v
8 passed in 7.78s

pytest tests/ -q
256 passed, 2 failed (test_50_odoo_export_tractorista.py — preexistente, no relacionado)
```

## Manual QA
1. Ir a `/reportes`, verificar que "Bonos mensuales" y "Hora ponderada 9h" aparecen como tarjetas seleccionables bajo "Tarjas — Contratistas".
2. Seleccionar solo "Bonos mensuales" con un rango de fechas, descargar → el PDF debe traer las filas de bonos de ese rango con la fila de suma total.
3. Seleccionar "Hora ponderada 9h" junto con otro reporte (ej. "Horas extra por persona") y descargar → un solo PDF con ambas secciones separadas por salto de página, cada una con su propio encabezado.
