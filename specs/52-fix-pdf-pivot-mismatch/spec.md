# PDFs de reportes de tarjas no coinciden con el formato/datos de la pantalla
# Path: specs/52-fix-pdf-pivot-mismatch/spec.md
issue: #52 · branch: 52-fix-pdf-pivot-mismatch · date: 2026-07-29

## What
El PDF de "Detalle contratista" mostraba una tabla completamente distinta a la pantalla (agregado total del rango en vez de un pivote fecha-por-fecha). Además, "Detalle tractorista" y "General tractorista" no tenían endpoint de PDF en absoluto (el botón de la pantalla apuntaba a una ruta inexistente → 404).

## Acceptance
- [x] Los PDFs que en pantalla muestran un pivote por fecha replican esa misma estructura (misma agrupación, mismas columnas de fecha, mismos montos que el Excel/pantalla)
- [x] Los títulos de cada PDF coinciden con el nombre del reporte en pantalla
- [x] Tests de regresión que verifican el fix contra la BD real

## Context
- Auditoría completa de los 9 reportes de tarjas (pantalla JS vs Excel vs PDF vs bulk-PDF de `/reportes`) — ver comentario/hallazgos en issue #52.
- **Solo "contratista" tenía el bug de agregación plana** (`GROUP BY` sin `fecha` en `download_tarjas_contratista_pdf`, tarjas_controller.py). El resto de reportes "pivote" (resumen-horas) ya coincidían; los reportes "flat" (general, detalle, jornadas-trabajador) nunca debían pivotear y ya estaban bien.
- **3 endpoints de PDF faltaban por completo** (404 al hacer clic): `detalle-tractorista`, `general-tractorista` (ambos agregados en este fix) y `resumen-persona-tractorista` (pivote, diferido — ver Deferred).
- Al reconstruir el pivote de fechas, apareció un bug NUEVO no relacionado con el original: con `table-layout` automático, una tabla con muchas columnas de fecha (incluso solo 7, una semana normal) hace que `reportlab` falle con `negative availWidth` — confirmado reproduciendo localmente.
- Al resolver eso con anchos fijos, un rango de fechas muy amplio (7 meses, ~200 columnas) todavía colapsa el texto por superposición — límite real del motor de renderizado, no algo solucionable con más CSS.

## Decisions
- Se portó exactamente la misma lógica de pivote de `download_tarjas_contratista_excel` (SQL con `GROUP BY ..., fecha::date` + pivote en Python) al PDF, en vez de reinventar el agrupamiento.
- El PDF ya no muestra columna "Contratista" (la pantalla tampoco la muestra en el pivote — solo el Excel la incluye); se prioriza igualar la pantalla, que es lo que pidió el usuario.
- Se agregó `_pivot_col_widths()`: calcula anchos inline (`table-layout:fixed`) — columnas fijas con % dado, columnas de fecha dividiendo el resto equitativamente. Debe aplicarse tanto en `<th>` (thead) como en cada `<td>` (tbody) — aplicarlo solo en el header no alcanza, causa superposición visual de texto entre columnas adyacentes (confirmado comparando con el patrón ya usado en `reports_controller.py`, que sí aplica la clase de ancho en ambos).
- Se agregó `_check_pivot_date_range()` (umbral `MAX_PIVOT_DATES=45`): si el rango pedido excede ese umbral, devuelve 400 con mensaje claro en vez de generar un PDF con texto ilegible. Aplica tanto al PDF de contratista como al de resumen-horas (mismo riesgo estructural).
- Los nuevos endpoints `detalle-tractorista`/`general-tractorista` PDF son reportes "flat" (no pivote) — se construyeron mirroreando exactamente la consulta SQL de sus respectivos Excel ya existentes.

## Implemented
### Controllers
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_PDF_CSS` — nueva clase `table.pivot-wide` (table-layout:fixed, fuente 6.5pt)
  - `_pivot_col_widths()` — helper nuevo, calcula anchos % por columna
  - `_check_pivot_date_range()` / `MAX_PIVOT_DATES` — guard nuevo contra rangos demasiado amplios
  - `download_tarjas_contratista_pdf` — reescrito: pivote por fecha (igual que Excel), título corregido a "Detalle contratista — Tarjas"
  - `download_tarjas_resumen_horas_pdf` — anchos fijos aplicados (mismo riesgo de crash que contratista)
  - `download_tarjas_detalle_tractorista_pdf` — endpoint nuevo (antes 404)
  - `download_tarjas_general_tractorista_pdf` — endpoint nuevo (antes 404)

### Tests
- `chatai/tests/test_52_fix_pdf_pivot_mismatch.py` — 9 tests: anchos suman 100%, guard de rango amplio, PDF de contratista renderiza sin error, rango amplio rechazado con 400 (no genera PDF ilegible), los 2 endpoints nuevos renderizan, isolation check (reporte flat "general" no se vio afectado)

## Routes
| Method | Path | Nota |
|--------|------|------|
| GET | /api/tarjas/contratista/download-pdf | Reescrito: pivote por fecha en vez de agregado plano |
| GET | /api/tarjas/detalle-tractorista/download-pdf | **Nuevo** — antes 404 |
| GET | /api/tarjas/general-tractorista/download-pdf | **Nuevo** — antes 404 |

## Tests
```
pytest tests/test_52_fix_pdf_pivot_mismatch.py -v
9 passed in 7.39s

pytest tests/ -v
154 passed in 13.99s
```
Cross-farm isolation: ✅ (test_52_general_pdf_still_flat_not_pivoted)

## Manual QA
1. En `/tarjas/contratista`, consultar con filtros Empresa=Talagante, Contratista=HERBI ML SPA, 22/07–28/07 → descargar PDF → debe verse idéntico a la pantalla (mismas columnas de fecha, mismos montos por trabajador/labor).
2. En `/tarjas/detalle-tractorista` y `/tarjas/general-tractorista`, hacer clic en "PDF" → debe descargar un archivo válido (antes daba 404/error de red).
3. En `/tarjas/contratista`, seleccionar un rango de más de 45 días con datos → el PDF debe fallar con un mensaje claro pidiendo acortar el rango, no un archivo con texto ilegible.

## Deferred
- `resumen-persona-tractorista` no tiene endpoint de PDF (mismo tipo de gap que los dos agregados aquí) — no incluido en este PR por alcance/tiempo; abrir issue de seguimiento si se necesita.
- Discrepancia de dimensión secundaria en `resumen-persona-tractorista`: la pantalla pivotea por (máquina, horas_extras), pero su Excel y el bulk-PDF de `/reportes` pivotean por `tipo_pago` — hallazgo de la auditoría, no corregido en este PR (requiere decisión de negocio sobre cuál agrupación es la correcta).
