# Spec: Agregar referencia_interna y producto_con_referencia a vw_apuntes_analiticos_desglosados

**Issue:** #148
**Branch:** `148-referencia-interna-producto`
**Labels:** enhancement

---

## What

La vista BigQuery `ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`
ya expone `producto` (issue #144) pero no expone la referencia interna (código
Odoo del catálogo). Hay que agregar:
1. `referencia_interna`: código interno del producto (`Producto.default_code`).
2. `producto_con_referencia`: `referencia_interna` concatenada con `producto`.

---

## Acceptance Criteria

- [x] La vista incluye `referencia_interna` poblada desde `Producto.default_code`
      vía el mismo JOIN ya existente (`p.id = ad.product_id`).
- [x] La vista incluye `producto_con_referencia` = referencia interna + nombre del producto.
- [x] Las columnas existentes no se renombran ni se eliminan.
- [x] El DDL persistido en `sql/bigquery/vw_apuntes_analiticos_desglosados.sql` se actualiza.
- [x] La vista se re-aplica en BigQuery (`CREATE OR REPLACE VIEW`).
- [x] Tests de regresión sobre el SQL persistido.
- [x] El system prompt del Chat IA menciona las columnas nuevas.

---

## Context

Precedente directo: issue #144 (spec en `specs/144-add-producto-column/spec.md`)
agregó `producto` a la misma vista con el mismo patrón (JOIN a `Producto` sobre
`ad.product_id`, alias `p`, CTE `con_nombre`).

**Cobertura confirmada contra BigQuery live:** de 292.838 filas en la vista,
solo 9.706 (~3,3%) tienen `Producto.default_code` no vacío para su `product_id`
— misma limitación de catálogo documentada en #144 (`Producto` solo tiene ~96
templates vs ~2.100 `product_id` distintos; `Variantes_del_producto` no está
exportada).

**Feedback post-deploy del usuario:** un producto conocido (OXUS, código Odoo
"HER") no mostraba `referencia_interna` pese a que el código aparece
literalmente en el apunte contable como `"OCD2-00206: [HER] OXUS"`. Causa
raíz: `product_id` en `Reporte_Analitico` es el ID de la **variante** Odoo
(`product.product`), pero `Producto` solo tiene templates (`product.template`);
el JOIN por ID solo acierta quando el ID de variante coincide por accidente
con un ID de template. Se investigó agregar un fallback que extrae el código
entre corchetes de `name` cuando el catálogo no matchea. Se verificó contra
datos live que:
- Códigos como `[HER]`, `[PETR-002]`, `[BENC-002]`, `[COMISTAR-01]` son
  referencias reales (mayúsculas, sin espacios, patrón consistente con
  `Producto.default_code`), pero un mismo código puede repetirse en varios
  productos distintos (`[HER]` aparece en OXUS, RIPPER FULL, HERBADOX, BASTA
  14 SL) — es más una categoría que un SKU único por producto.
- Hay corchetes con texto libre que **no** son códigos: `[Contabilizado en
  2025-05-08]`, `[revertido]`, `[COMPRA ALVI]`, `[UBC: 7492]`. Se filtran
  exigiendo que el contenido sea solo mayúsculas/dígitos/`._-` sin espacios.

El usuario, informado del trade-off, eligió agregar el fallback pese a la
imprecisión de categoría-vs-SKU (issue reportada en conversación, no en
GitHub).

---

## Decisions

- `referencia_interna` se agrega en la CTE `con_nombre` (mismo nivel donde ya
  se calculan `_producto_catalogo` / `_producto_etiqueta`), normalizado con
  `NULLIF(TRIM(p.default_code), '')` para tratar strings vacíos como NULL.
- El SELECT final original (que calculaba `producto` con una expresión
  COALESCE) se convirtió en CTE `con_producto`, porque BigQuery no permite
  referenciar un alias de columna definido en el mismo nivel de SELECT.
  `producto_con_referencia` se calcula en un SELECT final nuevo, envolviendo
  `con_producto`, así puede referenciar tanto `referencia_interna` como
  `producto` ya resueltos.
- `producto_con_referencia` = `CONCAT(referencia_interna, ' - ', producto)`
  cuando hay referencia interna; si no, cae a `producto` solo (nunca deja la
  columna vacía si `producto` existe).
- `referencia_interna` = `COALESCE(Producto.default_code, código_entre_corchetes)`.
  El fallback usa `REGEXP_EXTRACT(ad.name, r'\[([A-Z][A-Z0-9._-]*)\]')` —
  requiere empezar con mayúscula y solo mayúsculas/dígitos/`._-`, sin
  espacios, para no capturar texto libre entre corchetes. Sube la cobertura
  de ~3,3% a ~9,9% (28.873 / 292.957 filas). Documentado como categoría, no
  SKU único, en el header del SQL y en el system prompt.
- Se agregan ambas columnas al final del SELECT (no se reordenan columnas
  existentes) para no romper consumidores por posición (Looker Studio,
  `vw_informe_gerencial_costos`, que hace `SELECT ad.*`).
- No se versiona `vw_informe_gerencial_costos` en este cambio (fuera de scope,
  igual que en #144).
- Tests offline contra el archivo SQL: no dependen de credenciales BQ.
- Isolation farm-to-farm: N/A (warehouse BigQuery compartido, sin `farm_id`).

---

## Implemented

- `sql/bigquery/vw_apuntes_analiticos_desglosados.sql` — DDL actualizado: `referencia_interna` y `producto_con_referencia`
- `chatai/backend/controllers/chat_controller.py` — system prompt documenta las columnas nuevas
- `chatai/tests/test_148_referencia_interna_producto.py` — 8 tests de regresión contra el SQL
- `specs/148-referencia-interna-producto/spec.md` — esta spec
- Vista live aplicada en BigQuery: primero sin fallback (job `c367b5e1-720a-4dfe-94c6-06a6fc6bf4ea`),
  luego con el fallback de código entre corchetes (job `cf1320eb-95c5-4f01-b4fe-d21f271d852d`, location `us-central1`)

---

## Tests

8 passed (nuevos) + 7 passed (regresión #144 sigue verde) · isolation: N/A (vista BigQuery compartida, sin tenant/farm)

```
cd chatai && pytest tests/test_148_referencia_interna_producto.py tests/test_144_add_producto_column.py -v
15 passed in 0.16s
```

Suite completa: `pytest tests/ -q` → 328 passed, 5 failed (preexistentes en `main`,
issues #112 y #50, no relacionados con este cambio — confirmado con `git stash`).

---

## Manual QA

1. Verificar que las columnas existen en BigQuery:
   ```sql
   SELECT column_name
   FROM `ace-scarab-484515-v1.odoo_data.INFORMATION_SCHEMA.COLUMNS`
   WHERE table_name = 'vw_apuntes_analiticos_desglosados'
     AND column_name IN ('referencia_interna', 'producto_con_referencia');
   ```
   Debe devolver 2 filas.

2. Ver referencia interna resuelta y su concatenación:
   ```sql
   SELECT product_id, name, producto, referencia_interna, producto_con_referencia
   FROM `ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`
   WHERE referencia_interna IS NOT NULL
   LIMIT 20;
   ```
   `producto_con_referencia` debe ser `"<referencia_interna> - <producto>"`.

3. Confirmar el fallback sin referencia interna:
   ```sql
   SELECT producto, referencia_interna, producto_con_referencia
   FROM `ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`
   WHERE referencia_interna IS NULL
   LIMIT 5;
   ```
   `producto_con_referencia` debe ser igual a `producto`.

4. En Chat IA, preguntar por costos usando la referencia interna del producto:
   el modelo debe usar `vw_apuntes_analiticos_desglosados` y las columnas
   `referencia_interna` / `producto_con_referencia`.
