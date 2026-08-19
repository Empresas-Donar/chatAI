# Línea incompleta al exportar Orden de Compra a Odoo (labor CANALETAS AGUAS LLUVIA sin mapear)
# Path: specs/128-fix-canaletas-labor-mapeo/spec.md
issue: #128 · branch: 128-fix-canaletas-labor-mapeo · date: 2026-08-19

## What
El export a Odoo (`/odoo/tarjas`) para KONTROLAG / HERBI ML SPA (12–18/08/2026) mostraba 1 línea "⚠ Incompleta": labor "CANALETAS AGUAS LLUVIA" sin fila en `appsheet.tarjas_labores`.

## Acceptance
- [x] Se agrega `('14.42', 'CANALETAS AGUAS LLUVIA')` a `appsheet.tarjas_labores`.
- [x] KONTROLAG / HERBI ML SPA (12–18/08/2026) exporta sin líneas incompletas.
- [x] Test de regresión.

## Context
- `appsheet.tarjas_pagos` tiene 7 filas con `labor = 'CANALETAS AGUAS LLUVIA'` (HERBI ML SPA / KONTROLAG, 11 y 12/08/2026), `id_labor IS NULL`.
- A diferencia del issue #124 (variante de puntuación), acá la labor no tenía ninguna fila en el catálogo — coincidencia exacta encontrada en BigQuery `odoo_data.Producto`: "CANALETAS AGUAS LLUVIA" → `default_code = 14.42`.
- `_sync_labores` (auto-map desde BigQuery) solo corre cuando alguien genera el export/preview para ese contratista+empresa+rango exacto — nadie lo había generado antes de este reporte, por eso nunca se disparó automáticamente pese a que el producto sí existe en Odoo.

## Decisions
- Mismo patrón que #32/#124: INSERT idempotente en un archivo SQL numerado, sin tocar la vista ni el controller — bug de dato de catálogo, no de lógica de join.
- Corrección inmediata aplicada directamente en producción antes de este commit (mismo flujo que #124); este PR deja el fix persistido en el repo.

## Implemented
- `sql/tarjas/21_insert_labor_canaletas.sql`
- `chatai/tests/test_128_fix_canaletas_labor_mapeo.py`

## Tests
```
pytest chatai/tests/test_128_fix_canaletas_labor_mapeo.py -v
6 passed in 0.05s
```
Cross-farm isolation: ✅ (`test_128_cross_farm_isolation`)

## Manual QA
1. `SELECT * FROM appsheet.tarjas_reporte_odoo WHERE "Vendedor"='HERBI ML SPA' AND nombre_campo='KONTROLAG' AND fecha BETWEEN '2026-08-12' AND '2026-08-18' AND "order_line/product_id" IS NULL;` → 0 filas (ya verificado en producción).
2. Abrir `/odoo/tarjas` con contratista HERBI ML SPA, empresa KONTROLAG, fechas 12/08–18/08/2026, descargar el Excel y confirmar que no aparece ninguna fila ⚠ Incompleta.
