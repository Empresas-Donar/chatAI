# Spec: Poblar id_labor en tarjas_pagos y migrar JOINs a clave numérica

**Issue:** #27
**Branch:** `27-poblar-id-labor-tarjas-pagos`
**Labels:** bug

---

## What

La columna `tarjas_pagos.id_labor` fue agregada pero todos sus valores son NULL.
El JOIN en `tarjas_reporte_odoo` sigue usando comparación de texto normalizado
(`REGEXP_REPLACE + LOWER`) sobre el nombre de la labor, lo que es frágil y ha
causado 2 incidentes en producción (issues #25 y #32).

Se requiere:
1. Hacer backfill de `tarjas_pagos.id_labor` usando el JOIN de texto normalizado ya existente.
2. Exponer `id_labor` en la vista `tarjas_reporte`.
3. Reescribir el JOIN primario en `tarjas_reporte_odoo` para usar `id_labor` (robusto),
   con el JOIN de texto normalizado como fallback para filas que aún tengan `id_labor = NULL`.

---

## Acceptance Criteria

- `tarjas_pagos.id_labor` queda poblado para todas las filas donde la labor existe
  en `tarjas_labores` (match por texto normalizado o por prefijo `[X.Y]` / `X.Y-`).
- `tarjas_reporte` expone la columna `id_labor`.
- `tarjas_reporte_odoo` usa `id_labor` como join primario y texto normalizado como fallback.
- Las exportaciones a Odoo siguen resolviendo correctamente para todos los contratistas
  existentes (no regresión).
- Test de regresión: el backfill de `id_labor` resuelve al menos una labor conocida.

---

## Context

**Tablas involucradas:**
- `appsheet.tarjas_pagos` — columna `id_labor TEXT` recién agregada, todos NULL
- `appsheet.tarjas_labores` — catálogo: `id_labor`, `codigo_labor`, `labor`
- `appsheet.tarjas_reporte` — vista sobre `tarjas_pagos` (no almacena datos)
- `appsheet.tarjas_reporte_odoo` — vista con JOIN frágil por texto normalizado

**Archivos modificados:**
- `sql/tarjas/04_backfill_id_labor.sql` — UPDATE backfill (nuevo)
- `sql/tarjas/01_views_reporte.sql` — `p.id_labor` agregado al SELECT
- `sql/tarjas/02_views_odoo.sql` — nuevo JOIN l0 por id_labor + fallback texto en l1/l2/l3

---

## Decisions

- El backfill es idempotente: solo actualiza filas con `id_labor IS NULL`, por lo que
  ejecutarlo múltiples veces es seguro.
- Los JOINs de texto (l1, l2, l3) en `02_views_odoo.sql` se restringen con
  `r.id_labor IS NULL` para evitar ambigüedad cuando l0 ya resolvió.
- Se mantienen los tres JOINs de texto como fallback para filas antiguas y para las
  filas donde AppSheet aún no escribe `id_labor` (dependencia de cambio en AppSheet).
- No se modifica ningún endpoint Python — el cambio es puramente en SQL y en la vista.

---

## Implemented

- `sql/tarjas/04_backfill_id_labor.sql` — UPDATE que puebla tarjas_pagos.id_labor con las
  tres estrategias de match (texto normalizado, prefijo [X.Y], prefijo X.Y-)
- `sql/tarjas/01_views_reporte.sql` — `p.id_labor` expuesto en el SELECT de tarjas_reporte
- `sql/tarjas/02_views_odoo.sql` — JOIN l0 directo por id_labor como prioridad máxima;
  l1/l2/l3 restringidos a `r.id_labor IS NULL` como fallback
- `chatai/tests/test_27_poblar_id_labor.py` — 10 tests de regresión

---

## Tests

10 passed, 0 failed · isolation: ✅ (test_cross_farm_id_labor_isolation verifica unicidad de id_labor en el catálogo)

---

## Manual QA

1. Ejecutar `04_backfill_id_labor.sql` en producción y verificar con:
   ```sql
   SELECT COUNT(*) AS total,
          COUNT(id_labor) AS con_id_labor,
          COUNT(*) - COUNT(id_labor) AS sin_id_labor
   FROM appsheet.tarjas_pagos
   WHERE labor IS NOT NULL;
   ```
   El campo `con_id_labor` debe aumentar significativamente (idealmente = total).

2. Ejecutar los dos `CREATE OR REPLACE VIEW` (01 y 02) y abrir `/odoo/tarjas`.
   Seleccionar cualquier contratista conocido (ej. MULTISERVICIOS BONHOMIA SPA / KONTROLAG,
   fechas 2026-07-15 a 2026-07-22). Todas las filas deben mantener su estado OK.

3. Verificar que una fila con `id_labor` ya poblado resuelve correctamente aunque
   se cambie el nombre de la labor en AppSheet:
   ```sql
   SELECT id_labor, labor, "order_line/product_id"
   FROM appsheet.tarjas_reporte_odoo
   WHERE fecha >= '2026-07-01'
   LIMIT 20;
   ```
   Las filas con `id_labor` no NULL deben tener `order_line/product_id` no NULL.
