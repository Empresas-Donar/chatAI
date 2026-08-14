# Agregar monto de horas extra y cuadro resumen al reporte de horas extra por persona
# Path: specs/105-horas-extra-monto/spec.md
issue: #105 · branch: 105-horas-extra-monto · date: 2026-08-14

## What
En el reporte "Detalle trabajador hora extra" (`/tarjas/resumen-horas`, "Horas extra por persona"):
1. La tabla ahora tiene una columna final "Monto" con el dinero que representa la hora extra de cada trabajador en el período consultado.
2. Arriba de la tabla hay un cuadro resumen con: total de horas extra, cantidad de trabajadores recibiendo horas extra, y total en dinero a pagar — todo según los filtros seleccionados.

Ambos cambios están tanto en la pantalla como en el PDF descargable.

## Acceptance
- [x] Columna "Monto" al final de la tabla, en pantalla y PDF, con el total en pesos por trabajador
- [x] Cuadro resumen arriba de la tabla (pantalla y PDF) con: horas extra totales, N° de trabajadores, monto total
- [x] El resumen y las columnas reflejan los filtros aplicados (fechas, empresa, tipo de pago, trabajador, contratista)

## Context
- La tabla `appsheet.tarjas_pagos` ya tiene una columna `total_hora_extra` (numeric) con el monto pagado por hora extra en cada registro — no se deriva ninguna tarifa, se suma igual que `horas_extras`. Verificado con datos reales: `total_hora_extra = horas_extras × valor_jornada` (ej. 1h × $3.400 = $3.400), consistente registro a registro.
- Sigue el trabajo del issue #97 (que ocultó a los trabajadores sin horas extra en este mismo reporte). El filtro de "solo trabajadores con horas extra > 0" ya existente se mantiene sin cambios; el cuadro resumen y el conteo de trabajadores se calculan **después** de aplicar ese filtro.
- Pantalla: el endpoint `GET /api/tarjas/resumen-horas` ahora también agrega `monto_hora_extra` a cada fila y devuelve un objeto `resumen` con los 3 totales — se calcula en el backend en vez de duplicar la agregación en JS.
- PDF: mismo patrón — SQL trae `monto`, se acumula por trabajador junto con `total`, y se arma un cuadro `.pdf-summary` con los 3 totales antes de la tabla.
- Excel **no** se tocó — el pedido fue específico a pantalla y PDF.
- El cuadro resumen en pantalla reutiliza la clase `.kpi-grid`/`.kpi-card` ya usada en `despacho_resumen.html` (Cloud Run dashboard de despachos), copiada a `tarjas_resumen_persona.css` porque ese CSS no estaba compartido entre templates.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_PDF_CSS` — nueva clase `.pdf-summary` (cuadro de 3 celdas)
  - `get_tarjas_resumen_horas()` — suma `total_hora_extra` como `monto_hora_extra` por fila; agrega `resumen: {total_horas, total_trabajadores, total_monto}` a la respuesta
  - `download_tarjas_resumen_horas_pdf()` — mismo agregado de `monto`; nueva columna "Monto" en la tabla; nuevo cuadro resumen HTML antes de la tabla

### Frontend
- `chatai/frontend/static/tarjas_resumen_horas.js`:
  - `fmtCLP` (Intl.NumberFormat es-CL) para formatear dinero, consistente con el resto de la app
  - `renderSummary()` — nueva función, puebla el cuadro de 3 KPIs
  - `renderPivot()` — acumula `monto` por trabajador/tipo_pago, agrega columna "Monto"
- `chatai/frontend/templates/tarjas_resumen_horas.html` — cuadro `.kpi-grid` con 3 `.kpi-card` arriba de la tabla
- `chatai/frontend/static/tarjas_resumen_persona.css` — estilos `.kpi-grid`/`.kpi-card`/`.kpi-label`/`.kpi-value` (copiados de `despacho_resumen.css`)

### Tests
- `chatai/tests/test_105_horas_extra_monto.py` — 4 tests contra la base de datos real (contratista `HERBI ML SPA`, 2026-07-01..2026-08-10: 4 trabajadores con horas extra, 25h totales, $85.000 totales): totales del resumen en pantalla, monto por fila coincide con `total_hora_extra` real, cuadro resumen visible en el texto del PDF, columna Monto visible en el PDF.

## Routes
Sin cambios de rutas — mismos endpoints, respuesta y HTML ampliados.

## Tests
```
pytest tests/test_105_horas_extra_monto.py -v
4 passed in 6.73s

pytest tests/ -q
248 passed, 2 failed (test_50_odoo_export_tractorista.py — preexistente, no relacionado)
```

## Manual QA
1. Ir a `/tarjas/resumen-horas`, filtrar por un contratista y rango de fechas con varios trabajadores con horas extra → el cuadro resumen debe mostrar el total de horas, N° de trabajadores y el monto total correctos, y cada fila de la tabla debe terminar en una columna "Monto" con el dinero de ese trabajador.
2. Descargar el PDF del mismo filtro → debe verse el mismo cuadro resumen (bajo la nota explicativa) y la misma columna "Monto" al final de la tabla.
3. Cambiar los filtros (fecha, trabajador, contratista) y verificar que el cuadro resumen se recalcula acorde a los nuevos resultados.
