# Spec: Labores 'ENSAYOS Y PRUEBAS' y 'MANTENCIÓN DE ESTRUCTURAS' sin mapeo — 11/11 líneas incompletas para BONHOMIA/KONTROLAG

**Issue:** #32
**Branch:** `32-labores-sin-mapeo-bonhomia`
**Labels:** bug

---

## What

Al exportar a Odoo para el contratista **MULTISERVICIOS BONHOMIA SPA** / empresa **KONTROLAG**
en el período 2026-07-15 → 2026-07-22, **todas las 11 líneas** aparecen como ⚠ Incompleta con
`ORDER_LINE/PRODUCT_ID` = `–`.

Las dos labores que usa BONHOMIA en ese período no existen en `appsheet.tarjas_labores`:

| Labor en tarjas_reporte        | Código Odoo | Nombre en Odoo (exacto)          |
|-------------------------------|-------------|----------------------------------|
| `ENSAYOS Y PRUEBAS`           | `14.41`     | `ENSAYOS Y PRUEBAS ` (trailing space) |
| `MANTENCIÓN DE ESTRUCTURAS`   | `14.40`     | `MANTENCIÓN DE ESTRUCTURAS ` (trailing space) |

Los CCs (K0111, K0120, K0126, K0128, K0135, K0143) están correctamente mapeados en `tarjas_cc`
— el `analytic_distribution` resuelve bien, solo falla el `product_id`.

**Causa raíz doble:**
1. Las dos labores nunca fueron insertadas en `tarjas_labores`.
2. La función `_sync_labores` que debería auto-mapearlas desde BigQuery falla porque el nombre
   en Odoo tiene un espacio al final (`"ENSAYOS Y PRUEBAS "` vs `"ENSAYOS Y PRUEBAS"`), lo que
   impide el match exacto en el WHERE. Además, el banner "BigQuery no disponible" indica que la
   conexión a BigQuery falla desde el entorno de producción, por lo que `_sync_labores` ni
   siquiera llega a ejecutar la query.

**Diferencia con #25:** El issue #25 afectó una sola labor por espacios adyacentes a paréntesis.
Este bug involucra labores completamente nuevas que nunca se cargaron, con un segundo vector
independiente: trailing space en los nombres de Odoo.

---

## Acceptance Criteria

- Las labores "ENSAYOS Y PRUEBAS" y "MANTENCIÓN DE ESTRUCTURAS" resuelven sus
  `order_line/product_id` como `14.41` y `14.40` respectivamente.
- Las 11 líneas de BONHOMIA/KONTROLAG pasan de ⚠ Incompleta a OK en la exportación.
- `_sync_labores` normaliza (TRIM) los nombres de Odoo antes de comparar, evitando
  que futuros productos con trailing space fallen silenciosamente.
- Test de regresión confirma el comportamiento.

---

## Context

**Vista afectada:** `sql/tarjas/02_views_odoo.sql` — JOIN l1, l2, l3 sobre `tarjas_labores`

**Función afectada:** `_sync_labores` en
`chatai/backend/controllers/purchase_orders_controller.py` línea ~87-95 — la query a
BigQuery usa `JSON_VALUE(p.name, '$.es_CL') IN (...)` sin TRIM, por lo que `"ENSAYOS Y PRUEBAS "`
no matchea `"ENSAYOS Y PRUEBAS"` y `matches` queda vacío.

**Fix mínimo:**
1. Insertar las dos labores en `appsheet.tarjas_labores` via migración SQL.
2. Corregir `_sync_labores` para aplicar `TRIM()` al nombre de Odoo en la comparación.

---

## Decisions

- Se insertan las dos labores directamente en `tarjas_labores` vía SQL de migración:
  es el mecanismo canónico (igual que las 111 labores existentes).
- En `_sync_labores`, se aplica `TRIM()` al `JSON_VALUE` en la query BigQuery para que
  el matching sea robusto ante trailing/leading spaces en Odoo.
- No se modifica la vista SQL `02_views_odoo.sql` — los JOINs ya usan TRIM y REGEXP_REPLACE;
  el problema era la ausencia de las filas en `tarjas_labores`, no la lógica de join.

---

## Implemented

- `sql/tarjas/03_insert_labores_bonhomia.sql` — INSERT de las dos labores faltantes
- `chatai/backend/controllers/purchase_orders_controller.py` — `_sync_labores`: aplica
  TRIM al nombre de Odoo en la query BigQuery antes de comparar
- `chatai/tests/test_32_labores_sin_mapeo_bonhomia.py` — tests de regresión

---

## Tests

8 passed, 0 failed · isolation: ✅ (test_cross_farm_isolation valida que los códigos 14.40/14.41 no colisionan con los códigos existentes de Donar/Talagante)

---

## Manual QA

1. Abrir `/odoo/tarjas`, seleccionar contratista MULTISERVICIOS BONHOMIA SPA, empresa KONTROLAG,
   fechas 2026-07-15 a 2026-07-22. Todas las filas deben mostrar estado OK (no ⚠ Incompleta).
2. Verificar que `ORDER_LINE/PRODUCT_ID` muestra `14.40` para las filas de
   "MANTENCIÓN DE ESTRUCTURAS" y `14.41` para "ENSAYOS Y PRUEBAS".
3. Descargar el xlsx: debe contener las 11 líneas correctamente mapeadas.
