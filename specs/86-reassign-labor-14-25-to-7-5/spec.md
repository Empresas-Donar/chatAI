# Reasignar labores ingresadas con código 14.25 al código 7.5
# Path: specs/86-reassign-labor-14-25-to-7-5/spec.md
issue: #86 · branch: 86-reassign-labor-14-25-to-7-5 · date: 2026-08-06

## What
Se reasignaron las filas de `appsheet.tarjas_pagos` ingresadas con `id_labor='14.25'` (REPARTIR. ABRIR. FLAMEAR. TENSAR. CLIPEAR Y FIJAR PLÁSTICO) al código correcto `id_labor='7.5'` (CONSTRUCCIÓN MACROTÚNELES), actualizando también el texto denormalizado de la columna `labor`.

## Acceptance
- [x] Todas las filas de `appsheet.tarjas_pagos` con `id_labor='14.25'` pasan a `id_labor='7.5'`
- [x] El texto de la columna `labor` en esas filas se actualiza a `'CONSTRUCCIÓN MACROTÚNELES'`
- [x] `tarjas_reporte` / `tarjas_reporte_odoo` (VIEWs) reflejan el cambio automáticamente
- [x] Script SQL versionado en `sql/tarjas/`
- [x] Test de regresión

## Context
- `tarjas_pagos.id_labor` / `labor` son texto libre, sin FK a `tarjas_labores` — la reasignación no se propaga sola, mismo patrón que issues #75 y #84.
- `appsheet.tarjas_labores` tiene ambos códigos como labores catalogadas distintas: id 81 `codigo_labor='14.25'` y id 36 `codigo_labor='7.5'` — confirmado que 7.5 es la labor correcta a la que deben apuntar estas filas.
- `tarjas_reporte_odoo` hace match exacto `id_labor -> tarjas_labores.id_labor` como primer nivel del fallback de 4 niveles documentado en `CLAUDE.md` — al cambiar `id_labor` a `'7.5'` el `codigo_labor` exportado a Odoo pasa a ser el de "CONSTRUCCIÓN MACROTÚNELES" automáticamente, sin tocar la vista.
- Verificado antes de aplicar: 13 filas con `id_labor='14.25'`, todas `nombre_campo='TALAGANTE'`, `contratista='HERBI ML SPA'`, `tipo_pago='Al dia'`, fechas 15/07, 23/07, 24/07 y 04/08/2026.
- Se dejó sin tocar el catálogo `tarjas_labores` (ambos códigos siguen existiendo como labores separadas) — el usuario pidió reasignar las filas ya ingresadas, no fusionar/eliminar el catálogo.

## Decisions
- Se actualizó también la columna `labor` (texto libre) además de `id_labor`, para que el nombre mostrado en reportes quede consistente con el código Odoo exportado (confirmado con el usuario antes de ejecutar).
- El UPDATE se ejecutó directamente contra producción antes de abrir el PR, y luego se versionó el script SQL para trazabilidad — mismo orden que #75 y #84.

## Implemented
### SQL
- `sql/tarjas/21_reassign_labor_14_25_to_7_5.sql` — 1 `UPDATE` idempotente. **Ya ejecutado contra la BD real.**

### Tests
- `chatai/tests/test_86_reassign_labor_14_25_to_7_5.py` — 5 tests: no quedan filas con `id_labor='14.25'`, el código nuevo tiene las 13 filas con el texto correcto, todas son TALAGANTE/HERBI ML SPA/Al dia (isolation), otros códigos de labor no se tocaron (isolation), el catálogo `tarjas_labores` quedó intacto.

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_86_reassign_labor_14_25_to_7_5.py -v
5 passed in 1.52s
```
Cross-farm isolation: ✅ (`test_86_reassigned_rows_are_all_talagante_herbi_al_dia_isolation`, `test_86_other_labores_untouched_isolation`)

## Manual QA
1. En los reportes de tarjas para TALAGANTE / HERBI ML SPA en julio-agosto 2026, confirmar que las 13 jornadas antes listadas como "REPARTIR. ABRIR. FLAMEAR..." ahora aparecen como "CONSTRUCCIÓN MACROTÚNELES".
2. Volver a generar el export a Odoo para ese contratista/campo y confirmar que el `product_id` corresponde al código `7.5`.
3. Confirmar que otras filas con labores del rango 14.x (ej. 14.1 ESTACADO) no cambiaron.
