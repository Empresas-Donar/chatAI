# Spec: Detalle tractorista vacío en agosto (Pendiente + total_tractor)

## Qué

`/tarjas/detalle-tractorista` consultaba `appsheet.tarjas_reporte` (solo `estado = 'Aprobado'`, monto = `total_pagar`). En agosto 2026 todas las tarjas tractorista están `Pendiente` y el monto vive en `total_tractor`, así que el rango 01/08–06/09 quedaba vacío. Pantalla, Excel y PDF pasan a `tarjas_pagos` + `SUM(total_tractor)`, igual que los otros reportes tractorista.

## Criterios de aceptación

- [x] `GET /api/tarjas/detalle-tractorista?fecha_inicio=2026-08-01&fecha_termino=2026-09-06` devuelve filas (no vacío)
- [x] El total de esa respuesta coincide con `SUM(total_tractor)` de `tarjas_pagos` en el mismo rango (incluye Pendiente)
- [x] Filtros, Excel y PDF usan la misma fuente (`tarjas_pagos` / `total_tractor`)
- [x] El reporte operacional `/tarjas/detalle` no cambia (sigue en `tarjas_reporte`)

## Contexto

- Issue: https://github.com/Empresas-Donar/chatAI/issues/152
- URL reportada: `/tarjas/detalle-tractorista?fil-from=2026-08-01&fil-to=2026-09-06`
- Vista `tarjas_reporte`: `WHERE estado = 'Aprobado'` y `total_labor = SUM(total_pagar)`
- Agosto tractorista: 194 filas, 0 Aprobadas
- `general-tractorista` / resumen persona tractorista ya leen `tarjas_pagos`

## Decisiones

- No filtrar por `estado`: incluir Aprobado y Pendiente, como el resto de reportes tractorista.
- Unitario = `SUM(total_tractor) / COUNT(*)` (jornada = una fila de `tarjas_pagos`).
- Un helper `_detalle_tractorista_where` + `_fetch_detalle_tractorista_rows` compartido por API, Excel y PDF (issue #116).

## Implementado

- `chatai/backend/controllers/tarjas_controller.py` — filters, JSON, Excel y `_build_detalle_tractorista_html`
- `chatai/tests/test_152_detalle_tractorista_pendiente.py`
- `specs/152-detalle-tractorista-pendiente/spec.md`

## Rutas

Sin cambio de contrato: mismos query params. Cambia la fuente SQL.

## Tests

`pytest chatai/tests/test_152_detalle_tractorista_pendiente.py -v`

## QA Manual

1. Abrir `/tarjas/detalle-tractorista?fil-from=2026-08-01&fil-to=2026-09-06` → resumen por contratista (RD SPA, C y G, Herbi ML) y detalle con montos.
2. Descargar Excel y PDF del mismo filtro → mismas filas/totales.
3. `/tarjas/detalle` (operacional, no tractorista) con el mismo rango sigue igual.
