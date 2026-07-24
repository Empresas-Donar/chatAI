# Spec: Recuperar vistas tarjas_reporte y tarjas_reporte_odoo

**Issue:** #35
**Branch:** `27-poblar-id-labor-tarjas-pagos`
**Labels:** bug

---

## What

Las vistas `appsheet.tarjas_reporte` y `appsheet.tarjas_reporte_odoo` fueron eliminadas
silenciosamente cuando el commit `3de2bfd` ejecutó un `ALTER COLUMN TYPE` en
`tarjas_pagos.id_labor` de `NUMERIC` a `TEXT` con `CASCADE`.

PostgreSQL elimina automáticamente todos los objetos dependientes al usar `CASCADE` en un
`ALTER TABLE … ALTER COLUMN TYPE`. Ambas vistas dependían de `tarjas_pagos.id_labor`.

Los archivos SQL con las definiciones ya están actualizados en el repositorio (usan
`id_labor TEXT`) pero nunca fueron re-ejecutados en producción luego del `ALTER`.

---

## Acceptance Criteria

- `appsheet.tarjas_reporte` existe en producción y devuelve filas correctas.
- `appsheet.tarjas_reporte_odoo` existe en producción y devuelve filas correctas.
- El endpoint `/odoo/tarjas` del API funciona sin error `relation does not exist`.
- Test de regresión: las dos vistas existen en el esquema `appsheet`.

---

## Context

**Causa raíz:** `ALTER TABLE appsheet.tarjas_pagos ALTER COLUMN id_labor TYPE TEXT CASCADE`
en el commit `3de2bfd` eliminó ambas vistas como efecto colateral de `CASCADE`.

**Archivos SQL con las definiciones actualizadas:**
- `sql/tarjas/01_views_reporte.sql` — define `appsheet.tarjas_reporte`
- `sql/tarjas/02_views_odoo.sql` — define `appsheet.tarjas_reporte_odoo`

**Dependencia entre vistas:** `tarjas_reporte_odoo` hace `FROM appsheet.tarjas_reporte r`,
por lo tanto `01_views_reporte.sql` debe ejecutarse antes que `02_views_odoo.sql`.

---

## Decisions

- Se re-ejecutan los archivos SQL en orden (`01` antes que `02`) usando `CREATE OR REPLACE VIEW`.
- Se descubrió un segundo bug: `02_views_odoo.sql` referenciaba `l0.id_labor` pero `tarjas_labores`
  no tenía esa columna. Se agregó `id_labor` como columna generada
  `GENERATED ALWAYS AS (codigo_labor) STORED` en `06_add_id_labor_to_labores.sql`.
  Esto es correcto porque `tarjas_pagos.id_labor` almacena el valor de `codigo_labor`
  (lo pone el trigger `set_id_labor()`), por lo que el JOIN `l0.id_labor = r.id_labor` queda válido.
- No se modifica ningún código Python — el cambio es exclusivamente en SQL.
- No se necesita migración Alembic porque las vistas no son modelos SQLAlchemy.
- La columna generada es idempotente: `ADD COLUMN IF NOT EXISTS`.

---

## Implemented

- `sql/tarjas/06_add_id_labor_to_labores.sql` — agrega columna generada `id_labor` a `tarjas_labores`
- `sql/tarjas/01_views_reporte.sql` — re-ejecutado en producción, recrea `appsheet.tarjas_reporte`
- `sql/tarjas/02_views_odoo.sql` — re-ejecutado en producción, recrea `appsheet.tarjas_reporte_odoo`
- `chatai/tests/test_35_recuperar_vistas_tarjas.py` — 8 tests de regresión

---

## Tests

8 passed, 0 failed · isolation: ✅ (test_35_cross_farm_isolation_tarjas_reporte_scoped verifica que no hay filas sin Aprobado en tarjas_reporte)

---

## Manual QA

1. Verificar que las vistas existen:
   ```sql
   SELECT relname FROM pg_class c
   JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'appsheet' AND relname IN ('tarjas_reporte', 'tarjas_reporte_odoo');
   ```
   Debe devolver 2 filas.

2. Consultar datos de muestra en `tarjas_reporte`:
   ```sql
   SELECT contratista, fecha, total_a_pagar
   FROM appsheet.tarjas_reporte
   ORDER BY fecha DESC
   LIMIT 5;
   ```
   Debe devolver filas sin error.

3. Abrir el endpoint `/odoo/tarjas` en el API con cualquier rango de fechas reciente
   (ej. `fecha_inicio=2026-07-01&fecha_fin=2026-07-22`). La respuesta debe ser 200 OK
   con datos de contratistas, sin el error `relation "appsheet.tarjas_reporte" does not exist`.
