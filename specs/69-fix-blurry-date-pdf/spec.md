# Fecha superpuesta con nombre del trabajador en PDF de detalle tractorista
# Path: specs/69-fix-blurry-date-pdf/spec.md
issue: #69 · branch: 69-fix-blurry-date-pdf · date: 2026-07-31

## What
La tabla plana (fecha → trabajador → labor) del PDF de `/odoo/tarjas-tractorista` no tenía anchos de columna fijos ni `table-layout:fixed`, causando que el texto de la fecha se superpusiera visualmente con el nombre del trabajador de la fila siguiente ("borrosa"/ilegible).

## Acceptance
- [x] La columna Fecha no se superpone con Trabajador en ningún renderizado del PDF
- [x] Se aplican anchos fijos consistentes en header y body (mismo patrón que la tabla "por operador" agregada en issue #67)
- [x] Test de regresión

## Context
- Reportado por el usuario tras el deploy de issue #67 (PR #68), al revisar el PDF real en `https://intranet.empresasdonar.cl/odoo/tarjas-tractorista`.
- Verificado visualmente: renderizando el PDF (`GET /api/tarjas/tractorista/download-pdf`, Ramón Díaz / Talagante / 01–31 julio 2026) a PNG con PyMuPDF, se veía literalmente el texto de la fecha (ej. "01/07/2026") superpuesto sobre el nombre del trabajador de la fila siguiente.
- La tabla "por operador" agregada en issue #67 en el mismo PDF **no** tenía este problema — ya usaba `table-layout:fixed` con anchos calculados vía `_pivot_col_widths`. Solo la tabla plana original (preexistente antes de #67) carecía de esto.
- Mismo patrón de causa raíz que issue #52: sin `table-layout:fixed` ni anchos explícitos, xhtml2pdf/reportlab autoajusta columnas por contenido y una columna angosta con contenido intermitente (la fecha solo aparece en la primera fila de cada grupo) colapsa y se superpone con la columna vecina.

## Decisions
- Se reutilizó el mismo enfoque ya validado en issue #52: `table-layout:fixed` en la clase CSS de la tabla, más anchos explícitos (%) tanto en cada `<th>` del `<thead>` como en cada `<td>` del `<tbody>` — aplicarlo solo en el header no alcanza (ya documentado en la spec de #52).
- Anchos elegidos: Fecha 12%, Trabajador 30%, Labor 33%, Total a pagar 25% (suma 100%).
- No se usó `_pivot_col_widths` (diseñado para pivotes con N columnas repetidas) porque esta tabla tiene una estructura fija de 4 columnas — anchos porcentuales directos son más simples y suficientes.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py` — `download_tarjas_tractorista_pdf`: agregado `table-layout: fixed` y `word-wrap: break-word` a `table.data`; anchos explícitos en cada `<th>` del header y cada `<td>` de las filas de datos, subtotal y total.

### Tests
- `chatai/tests/test_69_fix_blurry_date_pdf.py` — 4 tests: `table-layout:fixed` presente, anchos explícitos en el header, anchos explícitos repetidos en el body (regresión directa del patrón de #52), y que los anchos sumen 100%.

## Routes
N/A — mismo endpoint existente (`GET /api/tarjas/tractorista/download-pdf`), sin cambio de contrato.

## Tests
```
pytest tests/test_69_fix_blurry_date_pdf.py -v
4 passed in 0.05s

pytest tests/ -v
188 passed, 2 failed in 20.62s
```
Los 2 fallos (`test_50_odoo_export_tractorista.py`) son preexistentes en `main`, no relacionados con este fix.

Cross-farm isolation: N/A — corrección de layout CSS, no toca datos ni scoping.

## Manual QA
1. En `/odoo/tarjas-tractorista`, generar una orden para cualquier contratista/campo con varios trabajadores en el mismo día y descargar el PDF → la fecha debe verse claramente separada del nombre del trabajador, sin superposición.
2. Verificar con un rango de fechas que cruce meses (ej. 25/06 al 05/07) que el layout se mantiene legible.
3. Confirmar que la segunda tabla ("Tabla por operador", issue #67) sigue viéndose igual que antes (no debía tener este problema y no se tocó su CSS).
