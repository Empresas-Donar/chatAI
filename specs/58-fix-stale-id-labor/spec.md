# Fila sin mapear a Odoo por id_labor desactualizado
# Path: specs/58-fix-stale-id-labor/spec.md
issue: #58 · branch: 58-fix-stale-id-labor · date: 2026-07-30

## What
La vista previa de exportación a Odoo marcaba 1 fila como "Incompleta" para HERBI ML SPA / Isla de Maipo (22-28 julio 2026). Causa: `id_Resumen='87ae12dc'` tenía `id_labor='9.10'`, desactualizado respecto al `codigo_labor='9.1'` vigente en `tarjas_labores` para esa misma labor (SUPERVISOR HUERTO).

## Acceptance
- [x] `id_Resumen='87ae12dc'` queda con `id_labor='9.1'`
- [x] La vista previa de exportación para estos filtros ya no muestra filas incompletas por este motivo
- [x] Script de re-sincronización general versionado (complemento de `04_backfill_id_labor.sql`)
- [x] Test de regresión

## Context
- Vista `appsheet.tarjas_reporte_odoo` (02_views_odoo.sql) resuelve `order_line/product_id` via `id_labor`. Si `id_labor` no coincide con ningún `codigo_labor` de `tarjas_labores`, el `product_id` queda `NULL` → la fila se marca "Labor sin mapear en Odoo" en el preview (`purchase_orders_controller.py:628-640`).
- El trigger `trg_set_id_labor` (issue #27, `05_trigger_id_labor.sql`) solo recalcula `id_labor` en `INSERT` o `UPDATE OF labor` en `tarjas_pagos` — nunca reacciona a cambios posteriores en `tarjas_labores.codigo_labor`.
- El backfill original (`04_backfill_id_labor.sql`) solo cubre `id_labor IS NULL` — no toca un `id_labor` ya seteado pero desactualizado.
- Verificado: **1 sola fila** en toda la tabla tenía este desajuste (comparando `id_labor` actual vs `codigo_labor` vigente para el texto exacto de la labor) — caso aislado, no sistémico. Confirmado además que las otras 4 filas de "SUPERVISOR HUERTO" del mismo contratista/campo en el mismo rango (22, 24, 27, 28 julio) ya usaban correctamente `id_labor='9.1'`.

## Decisions
- Se agregó `12_resync_stale_id_labor.sql` como complemento general de `04_backfill_id_labor.sql`: en vez de llenar solo `NULL`, resincroniza cualquier fila donde `id_labor` ya no coincide con el `codigo_labor` vigente — cubre este caso y previene que futuras correcciones al catálogo `tarjas_labores` dejen filas antiguas "huérfanas" en silencio.
- No se modificó el trigger `trg_set_id_labor` ni se agregó un trigger en `tarjas_labores` para cascadear cambios automáticamente — dado que hoy es un caso aislado (1 fila), un trigger adicional sería sobre-ingeniería; el script de resync general cubre la necesidad actual y puede re-ejecutarse manualmente si se detectan más casos.

## Implemented
### SQL
- `sql/tarjas/12_resync_stale_id_labor.sql` — 1 UPDATE idempotente (JOIN por texto de labor, corrige cualquier `id_labor` desactualizado). **Ya ejecutado contra `donar_prod`.**

### Tests
- `chatai/tests/test_58_fix_stale_id_labor.py` — 4 tests: 0 desajustes de `id_labor` restantes en toda la tabla, la fila específica corregida, la vista Odoo ya no tiene `product_id` NULL para el rango reportado, isolation check (`tarjas_labores` no se tocó)

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_58_fix_stale_id_labor.py -v
4 passed in 1.45s

pytest tests/ -v
167 passed in 20.66s
```
Cross-farm isolation: ✅ (test_58_cross_table_isolation_tarjas_labores_untouched)

## Manual QA
1. En `https://intranet.empresasdonar.cl/odoo/tarjas?inp-date-from=2026-07-22&inp-date-to=2026-07-28&sel-contractor=HERBI+ML+SPA&sel-company=ISLA+DE+MAIPO`, generar la vista previa → debe mostrar 10/10 completas, 0 incompletas.
2. `SELECT id_labor FROM appsheet.tarjas_pagos WHERE "id_Resumen"='87ae12dc'` → `'9.1'`.
