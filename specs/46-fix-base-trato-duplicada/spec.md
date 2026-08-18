# Corregir 60 tarjas de trato con base_trato duplicada el mismo día
# Path: specs/46-fix-base-trato-duplicada/spec.md
issue: #46 · branch: 46-fix-base-trato-duplicada · date: 2026-07-28

## What
60 registros en `appsheet.tarjas_pagos` (`tipo_pago='trato'`) tenían `base_trato` asignada más de una vez el mismo día cuando el trabajador realizó varias labores de tipo trato en la misma jornada — la base solo corresponde a la primera labor del día. Se corrigió `base_trato=0` en las labores duplicadas y se recalcularon `total_trato`, `total_trabajado`, `total_contratista` y `total_pagar`.

## Acceptance
- [x] Las 60 filas quedan con `base_trato=0` y los montos recalculados según lo verificado
- [x] Script SQL versionado en `sql/tarjas/10_fix_base_trato_duplicada.sql`
- [x] Test de regresión que verifica las 60 filas post-fix

## Context
- Tabla: `appsheet.tarjas_pagos`, filtro `tipo_pago='trato'`
- Fórmula confirmada (issue #42): `total_trato = base_trato + rendimiento × valor_trato`; markup de contratista ≈ 45% de `total_trato`
- El script de corrección fue entregado ya elaborado (60 sentencias UPDATE con `id_Resumen` explícitos), no derivado por mí desde cero — se verificó exhaustivamente antes de ejecutar (ver Decisions).

## Decisions
- **Verificación pre-ejecución** (antes de tocar producción): confirmé que las 60 `id_Resumen` existen, que las 60 tienen `base_trato=15000` (el valor duplicado) y `tipo_pago='trato'`, y validé programáticamente cada fila propuesta contra las fórmulas conocidas — 0 discrepancias en 60 filas × 4 chequeos (fórmula `total_trato`, markup ~45%, `total_trabajado`, consistencia con el desfase de redondeo preexistente en 15 filas de `rendimiento` fraccionario).
- El script original usaba `base_trato='0'` (string) y sin schema (`tarjas_pagos`); se corrigió a `base_trato=0` (numeric) y `appsheet.tarjas_pagos` al versionarlo.
- **Bug encontrado durante la verificación post-fix**: el script actualiza `total_contratista` pero no `contratista_trato`, dejando ambos campos desincronizados en las 60 filas (re-introduciendo el bug corregido en issue #42). Se corrigió con un UPDATE adicional (`contratista_trato = total_contratista`, dado que `contratista_jornada=0` en las 60) y se agregó como paso final del script versionado + test de regresión dedicado.
- Ejecutado directamente contra `donar_prod` con verificación antes/después.

## Implemented
### SQL
- `sql/tarjas/10_fix_base_trato_duplicada.sql` — 60 UPDATE de corrección + 1 UPDATE de sincronización `contratista_trato`. **Ya ejecutado contra `donar_prod`.**

### Tests
- `chatai/tests/test_46_fix_base_trato_duplicada.py` — 6 tests: `base_trato=0`, montos recalculados, fórmula `total_trato`, markup ~45%, sincronización `contratista_trato` (regresión del bug encontrado), isolation check

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_46_fix_base_trato_duplicada.py tests/test_42_fix_tarjas_data_sync.py -v
11 passed in 1.72s

pytest tests/ -v
160 passed in 8.11s
```
Cross-farm isolation: ✅ (test_46_cross_table_isolation_only_tarjas_pagos_touched)

## Manual QA
1. `SELECT count(*) FROM appsheet.tarjas_pagos WHERE base_trato=0 AND "id_Resumen" IN (...)` → 60.
2. `SELECT count(*) FROM appsheet.tarjas_pagos WHERE contratista_trato != total_contratista AND "id_Resumen" IN (...)` → 0.
3. Suma de `total_pagar` antes/después de las 60 filas: \$1.894.376 → \$589.376 (reducción de \$1.305.000, ≈\$21.750/fila = base duplicada \$15.000 + 45% markup — coincide con lo esperado).
