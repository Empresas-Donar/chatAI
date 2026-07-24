# Spec: Corregir tipos de dato numéricos en tarjas_pagos

**Issue:** #38
**Branch:** `38-fix-numeric-types-tarjas`
**Labels:** bug

---

## What

Las columnas `horas_extras`, `rendimiento` y `horas_trabajadas` en `appsheet.tarjas_pagos`
tienen tipo `TEXT` en lugar de `NUMERIC`. Esto fuerza a todo el código Python y a las vistas
SQL a usar expresiones defensivas con regex (`CASE WHEN col ~ '^[0-9]+...' THEN col::NUMERIC`)
en lugar de operar directamente sobre los valores numéricos.

La tabla `tarjas_det_supervisor` solo tiene 4 columnas (todas TEXT de identificación:
`id_detalle`, `id_supervisor`, `id_trabajador`, `actualizacion`) — ninguna numérica que corregir.

---

## Acceptance Criteria

1. Las columnas `horas_extras`, `rendimiento` y `horas_trabajadas` en `appsheet.tarjas_pagos` son tipo `NUMERIC`.
2. La vista `tarjas_reporte` se recrea sin el casting defensivo de regex para `horas_trabajadas`.
3. El código Python en `tarjas_controller.py` elimina los patrones defensivos de regex para estas columnas.
4. Test de regresión verifica que las columnas son `NUMERIC` y que `SUM(horas_trabajadas)` devuelve resultado correcto.
5. La vista `tarjas_reporte_odoo` no requiere cambios (no referencia directamente estas columnas).

---

## Context

**Tablas involucradas:**
- `appsheet.tarjas_pagos` — columnas `horas_extras TEXT`, `rendimiento TEXT`, `horas_trabajadas TEXT`
- `appsheet.tarjas_reporte` — vista que castea `horas_trabajadas` con regex defensivo

**Valores actuales en producción:**
- `horas_trabajadas`: contiene decimales reales (ej. `6.5`, `4.5`, `2.5`) → tipo correcto: `NUMERIC`
- `horas_extras`: valores enteros y cero → tipo correcto: `NUMERIC`
- `rendimiento`: valores enteros (rendimiento en cajas/cajones) → tipo correcto: `NUMERIC`
- Verificado: 0 valores no casteables en las tres columnas

**Archivos a modificar:**
- `sql/tarjas/07_fix_numeric_types.sql` — ALTER TABLE migration (nuevo)
- `sql/tarjas/01_views_reporte.sql` — recrear vista sin casting defensivo
- `chatai/backend/controllers/tarjas_controller.py` — eliminar patrones regex defensivos
- `chatai/tests/test_38_fix_numeric_types.py` — test de regresión (nuevo)

---

## Decisions

- Se usa `NUMERIC` (no `INTEGER`) para las tres columnas porque `horas_trabajadas` contiene
  decimales reales (6.5, 4.5, etc.) — se aplica el mismo tipo a las tres por consistencia.
- El casting en la vista pasa de `CASE WHEN ~ regex THEN ::NUMERIC ELSE 0 END` a un simple
  `COALESCE(SUM(horas_trabajadas), 0)` — equivalente pero limpio.
- Los patrones defensivos en el controlador se reemplazan por expresiones directas:
  `SUM(horas_trabajadas)` y `SUM(horas_extras)` sin regex.
- La vista `tarjas_reporte_odoo` no se toca porque no referencia directamente estas columnas
  (las recibe ya agregadas desde `tarjas_reporte`).
- El ALTER es seguro: verificado que todos los valores actuales en producción son casteables.

---

## Implemented

- `sql/tarjas/07_fix_numeric_types.sql` — ALTER COLUMN para horas_extras, rendimiento, horas_trabajadas en tarjas_pagos
- `sql/tarjas/01_views_reporte.sql` — vista tarjas_reporte sin casting defensivo de regex
- `chatai/backend/controllers/tarjas_controller.py` — eliminados patrones regex defensivos para horas_trabajadas y horas_extras
- `chatai/tests/test_38_fix_numeric_types.py` — test de regresión (columnas numéricas, SUM/AVG correctos)

---

## Tests

8 passed, 0 failed · isolation: ✅ (test_38_cross_table_isolation verifica que tarjas_det_supervisor no tiene columnas numéricas de horas)

---

## Manual QA

1. Ejecutar `07_fix_numeric_types.sql` en producción y verificar:
   ```sql
   SELECT column_name, data_type
   FROM information_schema.columns
   WHERE table_schema = 'appsheet' AND table_name = 'tarjas_pagos'
     AND column_name IN ('horas_extras', 'rendimiento', 'horas_trabajadas');
   -- Debe devolver data_type = 'numeric' para las tres
   ```

2. Ejecutar `01_views_reporte.sql` (CREATE OR REPLACE VIEW) y verificar que la vista sigue
   devolviendo datos correctos:
   ```sql
   SELECT contratista, SUM(horas_trabajadas) AS total_horas
   FROM appsheet.tarjas_reporte
   GROUP BY contratista
   ORDER BY total_horas DESC
   LIMIT 5;
   ```
   Debe devolver valores numéricos sin errores.

3. Abrir `/tarjas` en la UI, seleccionar cualquier contratista con horas (ej. con tipo_pago
   "Al día"), verificar que las columnas de horas muestran valores correctos (sin NaN, sin 0
   forzado donde había valores reales).
