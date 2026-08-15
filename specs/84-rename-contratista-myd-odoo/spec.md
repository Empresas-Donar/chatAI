# Renombrar contratista MYD SPA al nombre real de Odoo
# Path: specs/84-rename-contratista-myd-odoo/spec.md
issue: #84 · branch: 84-rename-contratista-myd-odoo · date: 2026-08-06

## What
Se corrigió el nombre del contratista "MYD SPA" (campo Zúñiga) a su nombre real en Odoo, "PRESTACION DE SERVICIOS M Y D SPA", para que la exportación deje de fallar al no encontrar el partner.

## Acceptance
- [x] `appsheet.tarjas_contratistas.nombre` actualizado para el contratista MYD (campo Zúñiga)
- [x] Todas las filas de `appsheet.tarjas_pagos.contratista = 'MYD SPA'` pasan a `'PRESTACION DE SERVICIOS M Y D SPA'`
- [x] `tarjas_reporte` / `tarjas_reporte_odoo` (VIEWs) reflejan el cambio automáticamente
- [x] Script SQL versionado en `sql/tarjas/`
- [x] Test de regresión

## Context
- `tarjas_pagos.contratista` es texto libre, no hay FK a `tarjas_contratistas` — por eso renombrar solo el catálogo no alcanza (mismo patrón que issue #75).
- `tarjas_reporte_odoo` (`SELECT pg_get_viewdef`) usa `r.contratista` directamente como `"Vendedor"` y como `partner_id` en el export a Odoo — por eso el nombre corto "MYD SPA" no hacía match con el partner real.
- Verificado antes de aplicar: `tarjas_contratistas` tenía 1 fila (`id_contratista='54SA6ASS4'`, `id_campo=3` → Zúñiga, `nombre='MYD SPA'`); `tarjas_pagos` tenía 26 filas con `contratista='MYD SPA'`, todas `nombre_campo='ZUÑIGA'` y `tipo_pago='trato'`.
- Búsqueda exhaustiva sobre todas las columnas `text`/`varchar` del schema `appsheet` para "MYD": sin coincidencias en `tarjas_bono_mensual` ni en las tablas `cosecha_*` (módulo de cosecha, no relacionado).

## Decisions
- Se usó `id_contratista` exacto (no `ILIKE` sobre `nombre`) para el UPDATE de `tarjas_contratistas`, porque solo había una fila y el id es la clave real de la tabla.
- Se usó `ILIKE` en el `WHERE` de `tarjas_pagos` para cubrir variantes de mayúsculas, siguiendo el mismo criterio del fix de issue #75.
- El UPDATE se ejecutó directamente contra producción antes de abrir el PR (urgencia: exportación a Odoo bloqueada), y luego se versionó el script SQL para trazabilidad — mismo orden que #75.

## Implemented
### SQL
- `sql/tarjas/20_rename_contratista_myd.sql` — 2 `UPDATE` idempotentes. **Ya ejecutado contra la BD real.**

### Tests
- `chatai/tests/test_84_rename_contratista_myd.py` — 5 tests: no quedan filas con "MYD SPA", el nombre nuevo tiene las 26 filas, todas son campo Zúñiga/tipo_pago trato (isolation), el catálogo `tarjas_contratistas` quedó actualizado, otros contratistas no se tocaron (isolation).

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_84_rename_contratista_myd.py -v
5 passed in 1.43s
```
Cross-farm isolation: ✅ (`test_84_renamed_rows_are_all_zuniga_trato_isolation`, `test_84_other_contratistas_untouched_isolation`)

## Manual QA
1. Volver a generar/exportar la orden de trato para "PRESTACION DE SERVICIOS M Y D SPA" / Zúñiga en el rango de fechas del Excel original y confirmar que Odoo ahora reconoce el partner.
2. Confirmar que el filtro de contratista en las pantallas de tarjas ya no ofrece "MYD SPA" como opción, sino el nombre nuevo.
3. Revisar que los montos/jornadas de las 26 filas no cambiaron, solo el nombre del contratista.
