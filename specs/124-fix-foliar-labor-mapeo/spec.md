# Líneas incompletas al exportar Orden de Compra a Odoo (labor FOLIAR sin mapear)
# Path: specs/124-fix-foliar-labor-mapeo/spec.md
issue: #124 · branch: 124-fix-foliar-labor-mapeo · date: 2026-08-19

## What
El Excel de Orden de Compra a Odoo (`/odoo/tarjas`) excluye 2 líneas de HERBI ML SPA / TALAGANTE (17 y 18 de agosto de 2026) porque la labor `"APLIC  MANUAL FOLIAR ( bomba espalada)"` no tiene entrada en el catálogo `appsheet.tarjas_labores`.

## Acceptance
<!-- Copiado del issue #124 -->
- [x] Se agrega la variante de texto `"APLIC  MANUAL FOLIAR ( bomba espalada)"` al catálogo `appsheet.tarjas_labores`, apuntando al código Odoo existente `4.2`. (SQL listo en `sql/tarjas/20_insert_labor_foliar_bomba.sql`; falta ejecutarlo en producción — ver Manual QA paso 1)
- [ ] Tras el fix, las 2 líneas de HERBI ML SPA / TALAGANTE (17 y 18 de agosto de 2026) aparecen con `order_line/product_id` no nulo en `tarjas_reporte_odoo` y se incluyen en el export a Excel. (Verificable solo después de ejecutar el SQL en producción)
- [x] Test de regresión que documente el mapeo esperado.

## Context
- Endpoint real: `GET /odoo/tarjas` y `GET /api/purchase-orders/odoo-export` en `chatai/backend/controllers/purchase_orders_controller.py` (no en `tarjas_controller.py` — la URL reportada apunta a Purchase Orders, que reutiliza la vista `tarjas_reporte_odoo`).
- Vista: `sql/tarjas/02_views_odoo.sql` (`appsheet.tarjas_reporte_odoo`) — resuelve `order_line/product_id` con 4 niveles de fallback (l0 id_labor directo, l1 texto normalizado, l2 prefijo `[X.Y]`, l3 prefijo `X.Y-`).
- Catálogo: `appsheet.tarjas_labores` (columnas: `id` PK serial, `codigo_labor`, `labor`, `id_labor`). Sin índice único sobre `(codigo_labor, labor)` — los `INSERT ... ON CONFLICT DO NOTHING` existentes en el repo no deduplican realmente, solo siguen el patrón ya establecido.
- Confirmado contra producción (solo `SELECT`, sin escritura):
  - `appsheet.tarjas_pagos` tiene exactamente 2 filas con `labor = 'APLIC  MANUAL FOLIAR ( bomba espalada)'`, ambas de HERBI ML SPA / TALAGANTE, fechas 2026-08-17 y 2026-08-18, `id_labor IS NULL`.
  - `appsheet.tarjas_labores` no tiene esa cadena exacta; solo tiene `'APLIC MANUAL FOLIAR-BOMBA ESPALDA'` (código `4.2`) y `'APLIC FOLIAR TURBO'` (código `4.1`) — ninguna coincide tras la normalización de espacios/paréntesis del join l1.
  - La labor análoga `"APLIC MANUAL HERBICIDA (...)"` sí tiene 2 filas en el catálogo (con y sin doble espacio/paréntesis) apuntando al mismo `codigo_labor = 5.1` — exactamente el patrón que falta replicar para FOLIAR.
  - BigQuery `odoo_data.Producto` no tiene ningún producto con "FOLIAR" ni "APLIC" en el nombre → `_sync_labores` (auto-sync) no puede resolverlo automáticamente; requiere INSERT manual como en el issue #32.
- Precedente idéntico: issue #32 (`sql/tarjas/03_insert_labores_bonhomia.sql`, `chatai/tests/test_32_labores_sin_mapeo_bonhomia.py`) — mismo síntoma "⚠ Incompleta", misma causa (labor sin fila en `tarjas_labores`), mismo tipo de fix (INSERT del texto exacto apuntando al código Odoo correcto).

## Decisions
- Se reutiliza el `codigo_labor` existente `4.2` (ya usado por `"APLIC MANUAL FOLIAR-BOMBA ESPALDA"`) en vez de crear un código nuevo, porque ambas cadenas describen la misma labor Odoo (aplicación manual foliar con bomba de espalda) y no hay producto separado en BigQuery para la variante con paréntesis.
- Se sigue el patrón de `03_insert_labores_bonhomia.sql`: nuevo archivo SQL numerado (`sql/tarjas/20_insert_labor_foliar_bomba.sql`) con `INSERT ... ON CONFLICT DO NOTHING`, sin tocar la vista ni el controller — el bug es de datos de catálogo, no de lógica de join.
- No se modifica `_sync_labores` en este fix: BigQuery no tiene el producto, así que el auto-sync nunca habría podido resolverlo; ampliar el auto-sync queda fuera de alcance (no hay evidencia de que otros productos con paréntesis tengan el mismo problema).
- El archivo SQL queda commiteado para que el usuario lo ejecute manualmente contra producción (mismo flujo que los INSERTs previos de labores) — no se ejecutó ningún INSERT/UPDATE contra producción durante esta investigación, solo `SELECT`.

## Implemented
- `sql/tarjas/20_insert_labor_foliar_bomba.sql` — INSERT de la variante de texto faltante en `appsheet.tarjas_labores`.
- `chatai/tests/test_124_fix_foliar_labor_mapeo.py` — tests de regresión.

## Tests
```
pytest chatai/tests/test_124_fix_foliar_labor_mapeo.py -v
9 passed in 0.05s
```
Cross-farm isolation: ✅ (`test_124_cross_farm_isolation` — el código `4.2` no colisiona con códigos de otras labores/campos, ej. rango `14.x` de Kontrolag del issue #32)

## Manual QA
1. Ejecutar `sql/tarjas/20_insert_labor_foliar_bomba.sql` contra producción.
2. `SELECT id_labor, "Nombre Labor", "order_line/product_id" FROM appsheet.tarjas_reporte_odoo WHERE "Vendedor" = 'HERBI ML SPA' AND nombre_campo = 'TALAGANTE' AND fecha BETWEEN '2026-08-12' AND '2026-08-18' AND "order_line/product_id" IS NULL;` debe devolver 0 filas.
3. Abrir `/odoo/tarjas` con contratista HERBI ML SPA, empresa TALAGANTE, fechas 12/08/2026-18/08/2026, descargar el Excel y confirmar que aparece una línea con `order_line/product_id = 4.2` que incluye las jornadas del 17 y 18 de agosto (antes quedaban fuera y sumaban al `X-Excluded-Amount`).
