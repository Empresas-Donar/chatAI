# PDF de Detalle Operacional no incluye resumen ni gráfico
# Path: specs/96-pdf-detalle-resumen-grafico/spec.md
issue: #96 · branch: 96-pdf-detalle-resumen-grafico · date: 2026-08-13

## What
El PDF descargado desde "Detalle de la semana" (título interno "Detalle Operacional") ahora incluye la misma tabla Resumen y el mismo gráfico de torta por tipo de pago que se ven en pantalla, y el gráfico (en pantalla y en PDF) muestra el porcentaje fijo sobre cada porción, no solo en el tooltip.

## Acceptance
- [x] El PDF de Detalle Operacional incluye una tabla Resumen idéntica a la de pantalla (mismas columnas, mismo formato de moneda, fila Total).
- [x] El PDF incluye un gráfico de torta equivalente al de pantalla, como imagen estática, con los mismos colores por tipo de pago.
- [x] El gráfico en pantalla y en el PDF muestran el porcentaje fijo sobre cada porción, no solo en el tooltip.
- [x] El resumen y el gráfico del PDF se calculan con los mismos filtros aplicados al detalle (`_build_detalle_filters`).
- [x] Tests de regresión cubren que el PDF se genera sin excepciones y contiene el resumen.

## Context
- Pantalla: `chatai/frontend/templates/tarjas_detail.html` (bloque `td-summary-row`, líneas 72-100), `chatai/frontend/static/tarjas_detail.js` (`renderSummary` líneas 110-127, `renderChart` líneas 129-168), `chatai/frontend/static/tarjas_detail.css` (colores/badges `tipo-trato` `#3b82f6`, `tipo-aldia` `#f97316`).
- PDF: `chatai/backend/controllers/tarjas_controller.py`, `download_tarjas_detalle_pdf` (ruta `/api/tarjas/detalle/download-pdf`) — hoy solo arma `rows_html` (tabla Detalle), sin resumen ni gráfico.
- Query de resumen ya existe (duplicada) dentro de `get_tarjas_detail` (~línea 665-675): agrupa `tarjas_reporte` por `tipo_pago` sumando `total_labor`/`jornadas`. Se extrajo a un helper `_query_detalle_resumen` reutilizado por ambos endpoints.
- El PDF se genera con `xhtml2pdf`/`pisa` sobre HTML estático (`_render_pdf`, línea ~292) — no ejecuta JS/canvas, así que el gráfico se embebe como PNG base64 (mismo patrón que `_logo_b64()`, línea 149).
- `tipo_pago` en datos reales tiene más de 2 valores (`trato`, `Al dia`, `Tractorista`, `Bono` verificado contra la DB) — el frontend actual solo distingue color/badge para `trato` (azul) vs todo lo demás (naranja, sin badge para tipos fuera del mapa). El PDF replica exactamente esa misma lógica para que ambos sean "idénticos".

## Decisions
- El pie chart del PDF se genera con `PIL.ImageDraw.pieslice()` (sin agregar matplotlib): un arco por fila de `resumen`, mismo color que pantalla, con el `%` dibujado centrado sobre cada porción vía `ImageDraw.text(..., anchor="mm", stroke_width=2)` para legibilidad sobre cualquier color de fondo. Debajo del círculo se dibuja una leyenda simple (cuadro de color + etiqueta + %).
- Pillow se agrega explícitamente a `requirements.txt` — deja de ser una dependencia transitiva opcional (antes solo usada en `_logo_b64` con fallback silencioso a "").
- Si `resumen` viene vacío o el total es 0, no se renderiza la sección Resumen/Gráfico en el PDF (incluso si hay filas de Detalle) — evita un gráfico vacío o división por cero.
- En pantalla, las etiquetas de porcentaje fijas sobre el gráfico se implementan con un plugin inline de Chart.js (sin dependencia nueva vía CDN) que dibuja el texto centrado en cada slice usando la Canvas API, registrado localmente en `tarjas_detail.js` antes de crear el `Chart`.
- Formato de moneda del Resumen en PDF: se reutiliza el helper `_fmt_clp` ya usado en el resto de `tarjas_controller.py` (mismo patrón `$X.XXX.XXX` que `Intl.NumberFormat('es-CL', {style:'currency', currency:'CLP'})` produce en pantalla).
- Bug encontrado al probar `_pie_chart_b64` contra datos reales: la fuente por defecto de Pillow (`ImageFont.load_default`, incluso con `size=`) no tiene glifos para vocales acentuadas del español y renderiza "Día" como un cuadro/tofu ilegible. Se agregó `_ascii_fold()` (usa `unicodedata.normalize("NFKD", ...)` para quitar tildes) aplicado solo al texto de la leyenda dibujado directamente en el PNG — la tabla Resumen en HTML conserva la tilde normalmente, porque ahí el texto lo renderiza reportlab/xhtml2pdf con una fuente que sí soporta acentos.
- `ruff check` reporta ~60 hallazgos preexistentes en `tarjas_controller.py` (principalmente `BLE001` por `except Exception:` genérico, patrón ya usado en todo el archivo, p.ej. `_logo_b64`) que no corresponden a este issue — no se tocaron para mantener el diff mínimo. El código nuevo reutiliza ese mismo patrón por consistencia con el archivo existente.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`: helper `_query_detalle_resumen` (reemplaza la query duplicada dentro de `get_tarjas_detail`), helpers `_tipo_pago_label`/`_tipo_pago_color`/`_tipo_pago_badge_class` (mismos mapeos que `tarjas_detail.js`), `_ascii_fold` (quita tildes solo para el texto dibujado en el PNG), `_pie_chart_b64` (genera el PNG del gráfico con Pillow, incluye % por porción y leyenda), `_summary_table_html` (arma la tabla Resumen), `_PDF_CSS` extendido con estilos `.summary-wrap`/`.summary-table`/`.badge-trato`/`.badge-aldia`/`.chart-cell`, `download_tarjas_detalle_pdf` actualizado para calcular resumen/gráfico y renderizarlos antes de la tabla Detalle, `get_tarjas_detail` refactorizado para reusar `_query_detalle_resumen` en lugar de la query duplicada inline.
- `chatai/requirements.txt`: se agrega `Pillow>=10.1.0` explícito.

### Frontend
- `chatai/frontend/static/tarjas_detail.js`: nuevo plugin inline de Chart.js `percentLabelPlugin` que dibuja el `%` centrado sobre cada slice del pie usando la Canvas API (además del tooltip existente), registrado en `renderChart`.

### Tests
- `chatai/tests/test_96_pdf_detalle_resumen_grafico.py`

## Routes
Sin cambios de rutas — mismo endpoint `GET /api/tarjas/detalle/download-pdf`, ahora con más contenido en el PDF resultante.

## Tests
```
pytest tests/test_96_pdf_detalle_resumen_grafico.py -v
15 passed in ~6-9s

pytest tests/ -v
244 passed, 2 failed (test_50_odoo_export_tractorista.py — preexistentes,
no relacionados a este issue; fallan igual en HEAD sin este branch)
```
Cross-farm isolation: ✅ (`test_96_campo_filter_isolation_regression` — filtra el resumen/gráfico por `nombre_campo` (el concepto de "predio"/farm en esta plataforma) y verifica que el total de un campo no incluye datos de otro ni iguala el total sin filtrar)

## Manual QA
1. Ir a "Detalle de la semana", aplicar un rango de fechas con datos → verificar que en pantalla el gráfico de torta ahora muestra el `%` fijo sobre cada porción (no solo al hacer hover).
2. Con los mismos filtros, hacer clic en "PDF" → verificar que el PDF descargado incluye la tabla Resumen (mismas filas/montos que pantalla) y el gráfico de torta con los mismos colores y porcentajes visibles.
3. Cambiar los filtros (contratista, CC, tipo de pago) y repetir — el resumen/gráfico del PDF debe reflejar los mismos filtros aplicados al Detalle.

## Deferred
- No se tocan los demás PDFs de tarjas (general, contratista, tractorista, etc.) — fuera de alcance del issue.
- No se agrega matplotlib ni otra librería de gráficos nueva — se usa Pillow (ya presente) para mantener el PDF liviano.
