# Corregir 65 tarjas de tractoristas con jornada lunes-sábado mal aplicada
# Path: specs/45-fix-tractorista-jornada/spec.md
issue: #45 · branch: 45-fix-tractorista-jornada · date: 2026-07-28

## What
65 registros de tractoristas (`appsheet.tarjas_pagos`, estado `Pendiente`) fueron ingresados con la jornada "lunes a sábado" (`horas_trabajadas=9.00`) en fechas que en realidad corresponden a lunes-viernes. Se corrigieron a `horas_trabajadas=7.5` y se recalcularon los montos según la regla de negocio correspondiente a cada tipo de labor.

## Acceptance
- [x] Las 65 filas quedan con `horas_trabajadas=7.5` y los montos (`total_tractor`, `total_trabajado`, `total_pagar`) corregidos según la tabla de reglas
- [x] Script SQL versionado en `sql/tarjas/09_fix_tractorista_jornada.sql`
- [x] Test de regresión que verifica los 65 registros post-fix

## Context
- Tabla: `appsheet.tarjas_pagos`, filtro `tipo_pago='Tractorista'`, `estado='Pendiente'`
- Reglas de negocio (aportadas por el equipo de operaciones, no derivables del esquema — no existe columna de licencia/certificado en la tabla):
  - **OPERARIO SOLO** / **Jornada Tractor simple**: tarifa igual en ambos esquemas, solo cambian las horas (9.00 → 7.5), el monto no cambia.
  - **Jornada Tractor normal**: el monto sí cambia — $72.000 (con licencia/certificado + bono) o $27.600 (sin licencia/certificado, sin bono).

## Decisions
- Se verificó el estado pre-fix de las 65 filas antes de ejecutar nada: todas en `Pendiente`/`Tractorista`/`horas_trabajadas=9`, coincidiendo con la premisa del reporte.
- Se verificó que OPERARIO SOLO / Jornada Tractor simple ya tenían el monto correcto (0 discrepancias) y que Jornada Tractor normal caía limpiamente en solo dos valores actuales ($61.000 o $23.000, sin atípicos) antes de aplicar — evita ejecutar una corrección basada en una premisa que ya no coincidiera con los datos reales.
- El script SQL original recibido usaba `tarjas_pagos` sin schema — se corrigió a `appsheet.tarjas_pagos` (nombre real de la tabla) al versionarlo.
- Ejecutado directamente contra `donar_prod` con verificación antes/después (65/65 en ambos casos).

## Implemented
### SQL
- `sql/tarjas/09_fix_tractorista_jornada.sql` — 65 UPDATE idempotentes por `id_Resumen`. **Ya ejecutado contra `donar_prod`.**

### Tests
- `chatai/tests/test_45_fix_tractorista_jornada.py` — 5 tests: horas corregidas, montos coinciden con la regla por tipo de labor, Jornada Tractor normal solo tiene 2 valores válidos, OPERARIO SOLO/simple sin cambio de monto, isolation check

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_45_fix_tractorista_jornada.py -v
5 passed in 1.94s

pytest tests/ -v
155 passed in 10.94s
```
Cross-farm isolation: ✅ (test_45_cross_table_isolation_no_other_rows_touched)

## Manual QA
1. `SELECT count(*) FROM appsheet.tarjas_pagos WHERE horas_trabajadas=7.5 AND tipo_pago='Tractorista' AND estado='Pendiente'` → debe incluir las 65 filas corregidas.
2. `SELECT DISTINCT total_tractor FROM appsheet.tarjas_pagos WHERE labor='Jornada Tractor normal' AND "id_Resumen" IN (...)` → solo 27600 o 72000.
3. Revisar en la UI (`/tarjas/detalle-tractorista` o `/tarjas/general-tractorista`) que los 65 registros muestren 7.5 horas y el monto correcto antes de aprobarlos.
