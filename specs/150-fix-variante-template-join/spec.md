# Spec: Corregir JOIN variante→plantilla en vw_apuntes_analiticos_desglosados

**Issue:** #150
**Branch:** `150-fix-variante-template-join`
**Labels:** enhancement

---

## What

Issues #144 y #148 agregaron `producto` y `referencia_interna` a
`vw_apuntes_analiticos_desglosados` usando `Producto.id = product_id`
directo. Ese JOIN es incorrecto: `product_id` en `Reporte_Analitico` es el ID
de la **variante** Odoo (`product.product`), no del template
(`product.template`) que exporta `Producto`. El JOIN solo acertaba por
coincidencia (~96 de ~2.111 `product_id` distintos).

Ahora existe `Variantes_del_producto` (modelo Odoo `product.product`,
recién configurado por el usuario en BigQuery Connector Pro), que permite el
JOIN correcto: `product_id → Variantes_del_producto.id → product_tmpl_id →
Producto.id`.

---

## Acceptance Criteria

- [x] `con_nombre` hace JOIN a `Variantes_del_producto` por `product_id`, y a
      `Producto` vía `product_tmpl_id` (no más `Producto.id = product_id` directo).
- [x] `referencia_interna` prioriza `Variantes_del_producto.default_code`, luego
      `Producto.default_code`, luego el fallback de código entre corchetes (#148).
- [x] `producto` sigue funcionando con la misma lógica de fallback (catálogo vs
      etiqueta limpia), pero ahora resuelve el catálogo correctamente para el
      100% de los `product_id` con variante existente (antes ~96/2.111).
- [x] Tests de regresión actualizados.
- [x] Vista re-aplicada en BigQuery y verificada contra datos reales (caso OXUS).

---

## Context

**Origen:** el usuario reportó que OXUS (código Odoo "HER") no mostraba
`referencia_interna` pese a aparecer `[HER]` en el apunte contable. La
investigación (documentada en `specs/148-referencia-interna-producto/spec.md`)
encontró la causa raíz: `product_id` es el ID de variante, `Producto` solo
tiene templates. Se agregó un fallback de texto como mitigación temporal.

**Resolución real:** el usuario configuró en BigQuery Connector Pro (app de
Odoo) la exportación del modelo `product.product` (mostrado en la UI como
"product_variant_combination" / "Variantes del producto") a la tabla
`Variantes_del_producto`. Había un registro con el mismo nombre pero mal
configurado (`Model: product_attr_exclusion_value_ids_rel`, columnas y
dominio de otro export copiados por error) que no era el correcto — se
identificó y se descartó. Tras un Hard Refresh sobre el export correcto, la
tabla apareció en BigQuery con 7.288 filas.

**Verificado contra BigQuery live:**
- `Variantes_del_producto.id` matchea el 100% de los 2.111 `product_id`
  distintos de `Reporte_Analitico` (antes ~96/2.111 vía `Producto` directo).
- OXUS: `id 35482 → product_tmpl_id 35618, default_code "HER"`;
  `id 33976 → product_tmpl_id 34090, default_code "HER"`. Ambos resuelven
  correctamente ahora, con o sin `[HER]` visible en la etiqueta del apunte.
- Cobertura de `referencia_interna` en la vista: 103.027 / 292.957 filas
  (~35%, sube de ~10% con solo el fallback de texto). El resto son productos
  que genuinamente no tienen `default_code` cargado en Odoo (dato real).
- Cobertura de `producto`: 291.973 / 292.957 filas (~99,7%).

---

## Decisions

- Se agrega `Variantes_del_producto v` al `con_nombre` CTE, joineado por
  `v.id = ad.product_id`. `Producto p` ahora se joinea vía
  `p.id = v.product_tmpl_id` (no más `p.id = ad.product_id`).
- `referencia_interna` = `COALESCE(v.default_code, p.default_code,
  fallback_corchetes)`. Se mantiene el fallback de texto de #148 para
  productos sin `default_code` en ningún nivel — sigue siendo el caso menos
  confiable (categoría, no SKU único), pero ahora es estrictamente el último
  recurso, no la única vía de cobertura no trivial.
- `producto` conserva exactamente la misma lógica de #144 (catálogo si
  aparece en la etiqueta → etiqueta limpia → catálogo); solo cambia de dónde
  saca el catálogo (ahora correcto vía variante).
- Se descartó el registro de exportación mal configurado
  (`Model: product_attr_exclusion_value_ids_rel` con nombre
  "Variantes_del_producto") — quedó fuera de este cambio de código, es
  configuración de Odoo, no del repo.
- Tests offline contra el archivo SQL: no dependen de credenciales BQ.
- Isolation farm-to-farm: N/A (warehouse BigQuery compartido, sin `farm_id`).

---

## Implemented

- `sql/bigquery/vw_apuntes_analiticos_desglosados.sql` — JOIN corregido vía `Variantes_del_producto`
- `chatai/backend/controllers/chat_controller.py` — system prompt documenta el JOIN correcto y nueva cobertura
- `chatai/tests/test_150_fix_variante_template_join.py` — 6 tests de regresión nuevos
- `chatai/tests/test_144_add_producto_column.py` — 1 assertion corregida (JOIN vía template, no product_id directo)
- `specs/150-fix-variante-template-join/spec.md` — esta spec
- Vista live aplicada en BigQuery (`CREATE OR REPLACE VIEW`, job `ef073bf2-4223-4f29-98a2-1c26386ef891`, location `us-central1`)

---

## Tests

21 passed (6 nuevos #150 + 8 #148 + 7 #144, todos verdes) · isolation: N/A (vista BigQuery compartida, sin tenant/farm)

```
cd chatai && pytest tests/test_150_fix_variante_template_join.py tests/test_148_referencia_interna_producto.py tests/test_144_add_producto_column.py -v
21 passed in 0.13s
```

Suite completa: `pytest tests/ -q` → 335 passed, 5 failed (preexistentes en
`main`, issues #112 y #50, no relacionados con este cambio).

---

## Manual QA

1. Verificar el JOIN correcto contra BigQuery:
   ```sql
   SELECT product_id, name, producto, referencia_interna, producto_con_referencia
   FROM `ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`
   WHERE UPPER(name) LIKE '%OXUS%'
   LIMIT 10;
   ```
   Todas las filas de OXUS deben mostrar `referencia_interna = "HER"`, con o
   sin `[HER]` visible en `name`.

2. Confirmar cobertura:
   ```sql
   SELECT
     COUNT(*) AS total,
     COUNTIF(referencia_interna IS NOT NULL) AS con_referencia,
     COUNTIF(producto IS NOT NULL) AS con_producto
   FROM `ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`;
   ```
   `con_referencia` debe ser ~35% del total, `con_producto` ~99,7%.

3. En Chat IA, preguntar por costos de OXUS o de un producto con código
   Odoo conocido: el modelo debe devolver `referencia_interna` consistente
   sin depender de si el código aparece literalmente en la etiqueta.
