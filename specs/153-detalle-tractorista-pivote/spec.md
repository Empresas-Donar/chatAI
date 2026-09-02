# Detalle tractorista: tabla pivote Looker (fecha × trabajador × labor)
# Path: specs/153-detalle-tractorista-pivote/spec.md
issue: #153 · branch: 153-detalle-tractorista-pivote · date: 2026-09-01

## What

`/tarjas/detalle-tractorista` debe dejar las dos tablas planas y mostrar el pivote anidado de Looker: contratista → trabajador → labor, filas = fechas con tarja, celdas = `SUM(total_tractor)`. Pantalla, Excel y PDF comparten el mismo builder.

## Acceptance

- [x] Un bloque pivote por contratista (cabecera con el nombre; hoy p. ej. AGROSERVICIOS C Y G SPA, ex Angel Celis / issue #75)
- [x] Tres filas de encabezado: contratista (colspan) → trabajador (colspan) → labor
- [x] Primera columna Fecha en **DD/MM/YYYY**; solo fechas con al menos una tarja tractorista (no inventar días vacíos del calendario)
- [x] Celda = `SUM(total_tractor)` de `appsheet.tarjas_pagos` para (fecha, trabajador, labor); vacía si no hay tarja
- [x] Última columna = total diario del contratista; pie **Suma total** con sumas de columna + gran total
- [x] Dinero es-CL (`$59.400`, 0 decimales)
- [x] Filtros actuales se mantienen (desde/hasta, empresa, campo, contratista, CC, labor)
- [x] Excel y PDF usan el mismo builder que el JSON de pantalla (patrón #52/#116)
- [x] Fuente: `tarjas_pagos` donde `LOWER(TRIM(tipo_pago)) = 'tractorista'`, incluye Pendiente y Aprobado (issue #152); no usar `tarjas_reporte` ni `total_pagar`
- [x] `/tarjas/detalle` (cuadrilla) no cambia

## Context

- Issue: https://github.com/Empresas-Donar/chatAI/issues/153
- Depende de #152 (`_detalle_tractorista_where` / `_fetch_detalle_tractorista_rows` sobre `tarjas_pagos` + `total_tractor`)
- Analogía: `_fetch_tractorista_pivot_rows` / `_build_tractorista_pivot` (orden de compra tractorista) y `tarjas_resumen_persona_tractorista.js`
- Archivos: `tarjas_controller.py`, `tarjas_detalle_tractorista.html/.js/.css`, `reports_controller.py` (sigue llamando `_build_detalle_tractorista_html`)
- No join a `tarjas_usuarios`
- En la DB actual, AGROSERVICIOS C Y G SPA no tiene tarjas tractorista en julio 2026 (el extracto Looker sí); agosto 2026-08-01..2026-09-06 sí (Pendiente). El gran total Looker $5.602.700 no se hardcodea.

## Decisions

- Un helper `_build_detalle_tractorista_pivots(rows)` arma un bloque por contratista. JSON, Excel y PDF lo llaman después de `_fetch_detalle_tractorista_rows` (misma fuente #152).
- Celdas ausentes quedan `None` (vacías en UI/Excel/PDF), no `$0`.
- PDF no usa `rowspan` (xhtml2pdf); pantalla sí (Fecha y Total en 3 filas). Excel usa celdas combinadas.
- Fechas en API siguen ISO; UI/Excel/PDF usan `_fmt_date_slash` / `DD/MM/YYYY`.
- `_check_pivot_date_range` se aplica al número de columnas (trabajador × labor), no a las fechas (crecen en vertical).

## Implemented

- `chatai/backend/controllers/tarjas_controller.py` — fetch de celdas, builder de pivotes, JSON, Excel y PDF
- `chatai/frontend/templates/tarjas_detalle_tractorista.html`
- `chatai/frontend/static/tarjas_detalle_tractorista.js`
- `chatai/frontend/static/tarjas_detalle_tractorista.css`
- `chatai/tests/test_153_detalle_tractorista_pivote.py`
- `chatai/tests/test_152_detalle_tractorista_pendiente.py` (se mantiene)
- `specs/153-detalle-tractorista-pivote/spec.md`

## Routes

| Method | Path | Nota |
|--------|------|------|
| GET | `/tarjas/detalle-tractorista` | Misma URL; layout pivote anidado |
| GET | `/api/tarjas/detalle-tractorista` | Respuesta `{pivots, total, jornadas, count}` |
| GET | `/api/tarjas/detalle-tractorista/download-excel` | Un bloque por contratista |
| GET | `/api/tarjas/detalle-tractorista/download-pdf` | Mismo HTML que bulk `/reportes` |

## Tests

```
cd chatai && .venv/bin/python -m pytest tests/test_153_detalle_tractorista_pivote.py tests/test_152_detalle_tractorista_pendiente.py -v
18 passed in 19.93s
```

Isolation: ✅ (`/tarjas/detalle` sigue en `tarjas_reporte`)

## Manual QA

1. Abrir `/tarjas/detalle-tractorista?fil-from=2026-08-01&fil-to=2026-09-06` → un pivote por contratista (AGROSERVICIOS C Y G SPA, HERBI ML SPA, SERVICIOS AGRICOLAS RD SPA), cabecera de 3 filas, fechas DD/MM/YYYY, pie Suma total.
2. Filtrar contratista AGROSERVICIOS C Y G SPA → un solo bloque; Excel y PDF con las mismas celdas/totales que la pantalla.
3. `/tarjas/detalle` (cuadrilla) con el mismo rango no cambia.
