# Actualizar nombre de contratista en pagos históricos
# Path: specs/75-rename-contratista-historico/spec.md
issue: #75 · branch: 75-rename-contratista-historico · date: 2026-07-31

## What
Se propagó a `appsheet.tarjas_pagos` el renombre de dos contratistas que el usuario ya había hecho en el catálogo maestro (`tarjas_contratistas`, vía AppSheet): "RAMÓN DIAZ" → "SERVICIOS AGRICOLAS RD SPA" y "ANGEL CELIS" → "AGROSERVICIOS C Y G SPA".

## Acceptance
- [x] Todas las filas de `tarjas_pagos` con `contratista='RAMÓN DIAZ'` pasan a `'SERVICIOS AGRICOLAS RD SPA'`
- [x] Todas las filas de `tarjas_pagos` con `contratista` que coincida con "Angel Celis" (cualquier variante de mayúsculas) pasan a `'AGROSERVICIOS C Y G SPA'`
- [x] `tarjas_reporte` (VIEW) refleja el cambio automáticamente, sin acción adicional
- [x] Tests de regresión

## Context
- `tarjas_pagos.contratista` es texto libre, no hay FK a `tarjas_contratistas` — por eso el rename del catálogo no se propaga solo.
- Verificado antes de aplicar: 69 filas con "RAMÓN DIAZ" (todas `tipo_pago='Tractorista'`, exactamente las mismas 69 filas trabajadas en los issues #64/#71), 0 filas con "Angel Celis".
- Verificado en `tarjas_contratistas`: ambos nombres nuevos ya existen ahí con varios `id_contratista` por campo (ej. `925a3536`/`21aed513`/`d5b528bc` → "SERVICIOS AGRICOLAS RD SPA"; `22bb91b6`/`861e97f912`/`861e97f922` → "AGROSERVICIOS C Y G SPA") — confirma que el catálogo ya está actualizado, solo faltaba propagar a `tarjas_pagos`.
- Verificado: `tarjas_reporte` es una `VIEW` sobre `tarjas_pagos`, se actualiza sola.
- Verificado: ninguna tabla `cosecha_*` (módulo de cosecha, distinto de tarjas) menciona estos nombres — sin impacto cruzado.
- Esto también resuelve la incógnita de la abreviatura `CYG` vista en `tarjas_maquina.tractorista` (issue #73): corresponde a "Agroservicios C y G SPA" (antes "Angel Celis").

## Decisions
- Se usó `ILIKE` (no `=`) en el `WHERE` para cubrir variantes de mayúsculas/acentos sin depender de que la codificación de terminal coincida exactamente con la de la BD.
- Se actualizaron `tests/test_67_pivot_table_screen_pdf.py` y `tests/test_71_maquina_column_pdf.py`, que usaban `CONTRATISTA = "RAMÓN DIAZ"` como parámetro de prueba contra la BD real — al ejecutar este rename esas 69 filas ya no existen bajo ese nombre, así que sus tests empezaron a fallar (0 filas devueltas) hasta actualizar la constante al nombre nuevo.

## Implemented
### SQL
- `sql/tarjas/17_rename_contratista_historico.sql` — 2 `UPDATE` idempotentes por nombre. **Ya ejecutado contra la BD real.**

### Tests
- `chatai/tests/test_75_rename_contratista_historico.py` — 5 tests: no quedan filas con "Ramón Diaz", "Servicios Agricolas RD SPA" tiene las 69 filas, todas son `tipo_pago='Tractorista'` (isolation), no quedan filas con "Angel Celis", otros contratistas no se tocaron (isolation).
- `chatai/tests/test_67_pivot_table_screen_pdf.py`, `chatai/tests/test_71_maquina_column_pdf.py` — actualizados para usar el nombre nuevo como parámetro de consulta.

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_75_rename_contratista_historico.py -v
5 passed in 1.44s

pytest tests/ -v
198 passed, 2 failed in 23.97s
```
Los 2 fallos (`test_50_odoo_export_tractorista.py`) son preexistentes en `main`, no relacionados con este fix.

Cross-farm isolation: ✅ (`test_75_other_contratistas_untouched_isolation`, `test_75_renamed_rows_are_all_tractorista_isolation`)

## Manual QA
1. En `/odoo/tarjas-tractorista`, generar una orden para contratista "SERVICIOS AGRICOLAS RD SPA" / Talagante o Isla de Maipo, 01–31 julio 2026 → debe traer las mismas 69 filas que antes mostraba "Ramón Diaz".
2. Confirmar que el filtro de contratista en la pantalla ya no ofrece "RAMÓN DIAZ" como opción (viene de `tarjas_pagos` vía `/api/tarjas/tractorista/filters`).
3. Revisar cualquier reporte/exportación ya generado para HERBI ML SPA / MULTISERVICIOS BONHOMIA SPA / etc. y confirmar que sus montos no cambiaron.
