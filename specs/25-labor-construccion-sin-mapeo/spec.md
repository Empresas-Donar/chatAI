# Spec: Labor con espacio extra tras paréntesis no mapea a product_id en exportación Odoo

**Issue:** #25
**Branch:** `25-labor-construccion-sin-mapeo`
**Labels:** bug

---

## What

La labor **"CONSTRUCCIÓN INFRAESTRUCTURA ( caminos, cercos, puentes)"** (con un espacio extra
después del paréntesis de apertura) aparece como **⚠ Incompleta** en la vista previa de
exportación a Odoo (`/odoo/tarjas`) porque `order_line/product_id` queda vacío.

**Causa raíz:** La tabla `appsheet.tarjas_labores` almacena el nombre como
`'CONSTRUCCIÓN INFRAESTRUCTURA (caminos, cercos, puentes)'` (sin espacio tras `(`), mientras
que `appsheet.tarjas_reporte` tiene `'CONSTRUCCIÓN INFRAESTRUCTURA ( caminos, cercos, puentes)'`
(con un espacio extra tras `(`). La normalización de la vista l1 colapsa múltiples espacios
consecutivos pero no elimina el espacio solitario después del `(`, por lo que los nombres
normalizados siguen siendo distintos y el JOIN no hace match.

---

## Acceptance Criteria

- La labor "CONSTRUCCIÓN INFRAESTRUCTURA ( caminos, cercos, puentes)" resuelve su
  `order_line/product_id` como `8.2` en la vista y aparece con estado OK en la exportación.
- Las demás labores no se ven afectadas.
- El mecanismo de auto-sync (`_sync_labores`) también trata esa labor como ya mapeada
  (no la reporta como unmapped).
- Test de regresión confirma que la discrepancia de espacio tras `(` se resuelve.

---

## Context

**Vista afectada:** `sql/tarjas/02_views_odoo.sql`, JOIN l1:

```sql
LEFT JOIN appsheet.tarjas_labores l1
       ON TRIM(REGEXP_REPLACE(LOWER(l1.labor), '\s+', ' ', 'g'))
        = TRIM(REGEXP_REPLACE(LOWER(r."Nombre Labor"), '\s+', ' ', 'g'))
```

`REGEXP_REPLACE(…, '\s+', ' ', 'g')` colapsa secuencias de **dos o más** espacios, pero
`( caminos` tiene exactamente un espacio después del `(` — no se colapsa.

**Función afectada:** `_sync_labores` en
`chatai/backend/controllers/purchase_orders_controller.py`, misma normalización en las
tres subqueries `COALESCE`.

**Fix mínimo:** agregar `REGEXP_REPLACE(…, '\(\s+', '(', 'g')` para eliminar espacios
tras `(` y `REGEXP_REPLACE(…, '\s+\)', ')', 'g')` para espacios antes de `)`, dentro de
la normalización de l1 (y en `_sync_labores`).

---

## Decisions

- Se mejora únicamente la normalización del JOIN l1 en la vista SQL y en `_sync_labores`.
- No se tocan las estrategias l2/l3 (prefijos numéricos) ni la tabla `tarjas_labores`.
- No se agrega un nuevo JOIN l4 — el problema es de normalización, no de estrategia de matching.

---

## Implemented

- `sql/tarjas/02_views_odoo.sql` — normalización de l1 ampliada: agrega dos `REGEXP_REPLACE`
  extra que eliminan espacios adyacentes a `(` y `)` antes de comparar (en ambos lados del ON)
- `chatai/backend/controllers/purchase_orders_controller.py` — `_sync_labores`: misma
  normalización extendida en la subquery l1 del COALESCE
- `chatai/tests/test_25_labor_construccion_sin_mapeo.py` — 8 tests de regresión

---

## Tests

8 passed, 0 failed · isolation: ✅ (test_cross_farm_isolation valida que la normalización
es determinista entre predios)

---

## Manual QA

1. Abrir `/odoo/tarjas`, seleccionar contratista HERBI ML SPA, campo TALAGANTE,
   fechas 2026-07-15 a 2026-07-21. En la vista previa, la fila
   "CONSTRUCCIÓN INFRAESTRUCTURA" debe mostrar `product_id = 8.2` y estado OK.
2. Descargar el xlsx: debe contener las filas de esa labor incluidas correctamente.
3. Ejecutar `pytest chatai/tests/test_25_labor_construccion_sin_mapeo.py -v` y
   verificar que todos los tests pasan.
