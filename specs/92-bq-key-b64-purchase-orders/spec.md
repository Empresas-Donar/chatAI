# Exportación a Odoo de tarjas contratistas falla por credencial BigQuery incompleta en producción
# Path: specs/92-bq-key-b64-purchase-orders/spec.md
issue: #92 · branch: 92-bq-key-b64-purchase-orders · date: 2026-08-13

## What
La exportación a Odoo de tarjas contratistas (contratista HERBI ML SPA, empresa KONTROLAG) muestra líneas incompletas y "BigQuery no disponible" en producción porque `_get_bq_client()` no soporta la credencial `BIGQUERY_KEY_B64` usada en Cloud Run.

## Acceptance
- [ ] `_get_bq_client()` en `purchase_orders_controller.py` soporta `BIGQUERY_KEY_B64` igual que `chat_controller.py`.
- [ ] En producción, la vista previa de exportación no muestra "BigQuery no disponible" cuando las credenciales están configuradas correctamente.
- [ ] Una labor nueva pero ya existente en el catálogo de productos de Odoo (ej. "CANALETAS AGUAS LLUVIA") se auto-mapea y no aparece como "Incompleta" al exportar.

## Context
- Módulo: `chatai/backend/controllers/purchase_orders_controller.py`, función `_get_bq_client()` (línea 42) usada por `_sync_labores`, `get_cc_status`, `get_export_preview` y `export_odoo_csv`.
- Patrón correcto ya existente: `chatai/backend/controllers/chat_controller.py::init()` (línea ~1245) — decodifica `BIGQUERY_KEY_B64` a un archivo temporal si está presente, si no cae a `BQ_KEY_PATH`. También replicado en `mcp_server/bigquery_client.py::_get_key_file()`.
- Mismo bug detectado en `chatai/backend/controllers/despacho_controller.py::_get_bq_client()` (línea 61) — fuera de alcance para este issue, ya reportado como hallazgo relacionado pero no incluido en el fix.
- Confirmado con consulta directa a BigQuery: el producto "CANALETAS AGUAS LLUVIA" (código `14.42`) existe en `ace-scarab-484515-v1.odoo_data.Producto`, por lo que el auto-mapeo de `_sync_labores` funcionaría si el cliente pudiera inicializarse.
- `_sync_labores()` solo se invoca desde `export_odoo_csv` (la descarga real del Excel), no desde `get_export_preview` — por diseño, la vista previa es de solo lectura.

## Decisions
- Se replica el mismo patrón de `chat_controller.py` (archivo temporal via `tempfile.NamedTemporaryFile`) en vez de extraer un helper compartido, para mantener el diff mínimo y consistente con el resto del código (cada controller ya tiene su propia copia de `_get_bq_client`).

## Implemented
### Controllers
- `chatai/backend/controllers/purchase_orders_controller.py`

## Routes
No se agregan ni cambian endpoints — mismo comportamiento, credenciales corregidas.

## Tests
Sin suite de tests automatizados para este controller (no hay `tests/test_purchase_orders.py` en el repo). Verificación manual en Manual QA.

## Manual QA
1. En producción (Cloud Run, con `BIGQUERY_KEY_B64` configurada), ir a `Odoo > Orden de compra — Tarjas contratistas`.
2. Filtrar contratista HERBI ML SPA, empresa KONTROLAG, 05/08/2026–11/08/2026, clic en "Generar orden".
3. La vista previa ya no debe mostrar "BigQuery no disponible"; la línea "CANALETAS AGUAS LLUVIA" debe aparecer como completa con `product_id = 14.42`.
4. Descargar el Excel y confirmar que la fila de "CANALETAS AGUAS LLUVIA" está incluida.

## Deferred
- Mismo fix en `despacho_controller.py::_get_bq_client()` (bug idéntico, no reportado en este issue).
