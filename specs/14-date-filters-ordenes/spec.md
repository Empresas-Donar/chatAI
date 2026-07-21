# Spec: Agregar filtros de fecha al endpoint GET /despacho/ordenes

**Issue:** #14
**Branch:** `14-date-filters-ordenes`
**Labels:** bug

---

## What

El endpoint `GET /api/despacho/ordenes` y su vista frontend en `/despacho/ordenes` carecen de filtros de rango de fechas.
Todas las otras vistas de despacho (`/despacho/resumen`, `/despacho/guia`, `/despacho/odoo`) aceptan `fecha_inicio` / `fecha_termino`.
Se agrega el mismo patrón: parámetros opcionales de fecha en el backend, dos inputs de fecha en el HTML, y sincronización de URL via `url-filters.js`.

---

## Acceptance Criteria

- [x] `GET /api/despacho/ordenes?fecha_inicio=YYYY-MM-DD&fecha_termino=YYYY-MM-DD` filtra correctamente por rango de fecha
- [x] Fechas con formato inválido retornan HTTP 400
- [x] El frontend muestra inputs Fecha Inicio / Fecha Término con default últimos 90 días
- [x] Los parámetros de fecha se sincronizan en la URL al hacer Consultar
- [x] El endpoint `/api/despacho/ordenes/download` también acepta y usa `fecha_inicio`/`fecha_termino`
- [x] Existe un test de regresión que verifica el filtrado por fecha

---

## Context

**Tabla afectada:** `appsheet.despacho_venta`
- Columna `fecha` es de tipo `TEXT` — se guarda como `MM/DD/YYYY HH:MM:SS` según el parseFecha() del JS actual
- Conversión necesaria: `TO_DATE(SPLIT_PART(fecha, ' ', 1), 'MM/DD/YYYY')` para comparar con rango BETWEEN

**Patrón existente (replicado de):**
- `/despacho/resumen` y `/despacho/guia`: `_DATE_RE.match()` para validar, `BETWEEN %s AND %s` en WHERE
- Frontend: `<input type="date" id="fil-from">` / `<input type="date" id="fil-to">`, `setDefaultDates()` con -90 días, `FILTER_IDS` incluye ambos inputs

---

## Decisions

- Los filtros de fecha son opcionales (no `Query(...)`): si se omiten, no se aplica filtro de fecha. Esto mantiene compatibilidad con bookmarks/URLs sin fechas y con el endpoint de filters que no necesita fechas.
- Se usa `TO_DATE(SPLIT_PART(fecha, ' ', 1), 'MM/DD/YYYY') BETWEEN %s AND %s` en vez de un cast directo: la columna `fecha` en `despacho_venta` es TEXT con formato `MM/DD/YYYY HH:MM:SS`, a diferencia de `despacho_ingreso` que tiene `fecha_limpia::date`.
- El frontend exige fecha antes de llamar a la API (`if (!from || !to) { showError... }`), pero el backend acepta solicitudes sin fechas para flexibilidad futura.
- El download CSV también pasa `fecha_inicio`/`fecha_termino` si están seteados, preservando la coherencia entre vista y descarga.

---

## Implemented

- `chatai/backend/controllers/despacho_controller.py` — `get_despacho_ordenes`: agrega `fecha_inicio`/`fecha_termino` params opcionales, validación con `_DATE_RE`, filtro SQL con `TO_DATE(SPLIT_PART(...))`. `download_despacho_ordenes`: mismo cambio.
- `chatai/frontend/templates/despacho_ordenes.html` — agrega inputs `fil-from` y `fil-to` antes de los selects existentes
- `chatai/frontend/static/despacho_ordenes.js` — agrega `setDefaultDates()` (últimos 90 días), actualiza `FILTER_IDS` para incluir `fil-from`/`fil-to`, lee fechas en `fetchOrdenes` y `btn-download`, valida que ambas fechas estén presentes antes de llamar API
- `chatai/tests/test_despacho_ordenes_date_filters.py` — 8 tests de regresión (análisis estático)

---

## Tests

8 passed, 0 failed · isolación: N/A (análisis estático, sin DB)

- `test_14_date_filters_ordenes_regression` — verifica que `get_despacho_ordenes` declara `fecha_inicio` y `fecha_termino`
- `test_14_date_sql_expression` — verifica que el SQL usa `TO_DATE` y `BETWEEN`
- `test_14_date_validation_400` — verifica que se usa `_DATE_RE` y se retorna 400 ante formato inválido
- `test_14_download_also_has_date_params` — verifica que el endpoint de descarga también tiene los params
- `test_14_js_sends_fecha_inicio` / `test_14_js_sends_fecha_termino` — verifica que el JS envía ambos params
- `test_14_js_has_default_dates` — verifica que el JS llama `setDefaultDates()`
- `test_14_js_filter_ids_include_dates` — verifica que `FILTER_IDS` incluye `fil-from`/`fil-to`

---

## Manual QA

1. Abrir `/despacho/ordenes`. Verificar que aparecen dos nuevos inputs de fecha (Fecha Inicio / Fecha Término) con valores pre-llenados (últimos 90 días). Hacer clic en "Consultar". Verificar que la tabla muestra órdenes y la URL incluye `fil-from=YYYY-MM-DD&fil-to=YYYY-MM-DD`.
2. Cambiar Fecha Inicio a una fecha muy reciente (ej. ayer) y Fecha Término a hoy. Hacer "Consultar". Verificar que la tabla se reduce o muestra "Sin resultados". Copiar la URL y abrirla en una pestaña nueva — los filtros deben estar pre-llenados y la consulta debe auto-ejecutarse con el mismo resultado.
3. Descargar CSV con "↓ CSV" y verificar que el archivo sólo contiene filas dentro del rango de fechas seleccionado.
