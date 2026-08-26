# Spec: Agregar columna producto a vw_apuntes_analiticos_desglosados

**Issue:** #144
**Branch:** `144-add-producto-column`
**Labels:** enhancement

---

## What

La vista BigQuery `ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`
desglosa `Reporte_Analitico` por centro de costo, pero no expone el nombre del
producto. Solo hereda `product_id` (INT64). La definición de la vista no estaba
en git: vivía únicamente en BigQuery.

Hay que:
1. Agregar la columna `producto` (nombre en español del catálogo Odoo).
2. Versionar el DDL completo en el repositorio.

---

## Acceptance Criteria

- [x] La vista incluye una columna `producto` poblada (catálogo si coincide con la etiqueta; si no, name del apunte).
- [x] Las columnas existentes no se renombran ni se eliminan.
- [x] El DDL queda en `sql/bigquery/vw_apuntes_analiticos_desglosados.sql`.
- [x] La vista se aplica en BigQuery (o queda documentado el comando si faltan permisos).
- [x] Test de regresión: el SQL persistido declara `CREATE OR REPLACE VIEW` y la columna `producto`.
- [x] El system prompt del Chat IA menciona esta vista y `producto`.

---

## Context

**Búsqueda GitHub / repo (confirmada):** ningún issue 1–137 menciona
`vw_apuntes_analiticos_desglosados`. Cero coincidencias en código/SQL/specs.
Issues cercanos: #77 (`CC_analiticos`), #7 (`Modelos_Distribucion_Analitica`),
#92/#94 (credenciales BQ). Esta es la documentación que faltaba.

**Ubicación live:** `ace-scarab-484515-v1.odoo_data` (dataset location `us-central1`).

**Columnas actuales (82, ahora 83):** `amount_residual` … `product_id` (pos. 19) … `name`
(descripción del apunte) … `distribucion_resuelta`, `origen_distribucion`,
`cc_id_str`, `porcentaje_asignado`, `pct_total_distribucion`, `balance_asignado`,
`debito_asignado`, `credito_asignado`, `empresa_nombre`, `cc_nombre`,
`cc_company_id`, `cc_codigo`, `cc_activo`, **`producto` (nueva, pos. 83)**.

**Vista dependiente (tampoco en git):** `vw_informe_gerencial_costos` hace
`SELECT ad.*` y extrae un producto sucio con regex sobre `name`
(`producto_ultra_limpio`). Agregar `producto` al final no rompe esa vista.

**Join de producto (confirmado contra schema live, no adivinado):**
- En Odoo, `account.move.line.product_id` → `product.product` (variante).
- Camino documentado en ChatAI: `product_id` → `Variantes_del_producto.id` →
  `Producto.id` via `product_tmpl_id` → `JSON_VALUE(name, '$.es_CL')`.
- **Live:** `Variantes_del_producto` no está exportada. `Producto` (template)
  tiene 96 filas vs 2.108 `product_id` distintos. El único JOIN posible es
  `Producto.id = product_id`.

---

## Decisions

- Se persiste el DDL original de la vista live y se le agrega `producto` al
  **final**, para no romper consumidores que seleccionan columnas por nombre
  (Looker Studio, `vw_informe_gerencial_costos`).
- JOIN: `Producto.id = ad.product_id` porque `Variantes_del_producto` no existe
  en `odoo_data`. El catálogo solo tiene ~96 templates y deja `producto` vacío
  en ~96% de las filas; además algunos IDs coinciden por accidente (variante vs
  template). Por eso `producto` es:
  1. nombre del catálogo **solo si** aparece en `name` del apunte;
  2. si no, `name` sin prefijos OC / órdenes MO / `[código]`;
  3. si no, el nombre del catálogo.
- Cobertura esperada con el fallback de etiqueta: ~290k / 291k filas.
- No se versiona `vw_informe_gerencial_costos` en este cambio (fuera de scope).
- Tests offline contra el archivo SQL: no dependen de credenciales BQ.
- Isolation farm-to-farm: N/A (warehouse BigQuery compartido, sin `farm_id`).

---

## Implemented

- `sql/bigquery/vw_apuntes_analiticos_desglosados.sql` — DDL versionado + columna `producto`
- `chatai/backend/controllers/chat_controller.py` — system prompt y tool `query_bigquery` documentan la vista
- `chatai/tests/test_144_add_producto_column.py` — 6 tests de regresión contra el SQL
- `specs/144-add-producto-column/spec.md` — esta spec
- Vista live aplicada en BigQuery (`CREATE OR REPLACE VIEW`, job `89b2df70-c4aa-421d-ac35-609aa4d74c2b`, location `us-central1`)

---

## Tests

6 passed, 0 failed · isolation: N/A (vista BigQuery compartida, sin tenant/farm)

```
cd chatai && pytest tests/test_144_add_producto_column.py -v
```

---

## Manual QA

1. Verificar que la columna existe en BigQuery:
   ```sql
   SELECT column_name
   FROM `ace-scarab-484515-v1.odoo_data.INFORMATION_SCHEMA.COLUMNS`
   WHERE table_name = 'vw_apuntes_analiticos_desglosados'
     AND column_name = 'producto';
   ```
   Debe devolver 1 fila.

2. Ver nombres resueltos vs descripción del apunte:
   ```sql
   SELECT product_id, name, producto
   FROM `ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`
   WHERE producto IS NOT NULL
   LIMIT 20;
   ```
   `producto` debe ser el nombre del catálogo (`es_CL`), no el `name` del asiento.

3. Re-aplicar el DDL (idempotente) si hace falta:
   ```bash
   python3 -c "
   from google.cloud import bigquery
   from google.oauth2 import service_account
   from pathlib import Path
   creds = service_account.Credentials.from_service_account_file(
       '/Users/bedomax/startups/donar/bigquery-odoo-key.json')
   client = bigquery.Client(project='ace-scarab-484515-v1', credentials=creds)
   ddl = Path('sql/bigquery/vw_apuntes_analiticos_desglosados.sql').read_text()
   client.query(ddl).result()
   print('ok')
   "
   ```

4. En Chat IA, preguntar costos por producto y CC: el modelo debe usar
   `vw_apuntes_analiticos_desglosados` y la columna `producto`.
