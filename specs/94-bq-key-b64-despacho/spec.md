# Sincronización de despacho falla por credencial BigQuery incompleta en producción
# Path: specs/94-bq-key-b64-despacho/spec.md
issue: #94 · branch: 94-bq-key-b64-despacho · date: 2026-08-13

## What
`_get_bq_client()` en `despacho_controller.py` no soporta `BIGQUERY_KEY_B64` (la única credencial disponible en Cloud Run), por lo que BigQuery nunca se inicializa en producción para este controller — mismo bug que #92, ya corregido en `purchase_orders_controller.py`.

## Acceptance
- [ ] `_get_bq_client()` en `despacho_controller.py` soporta `BIGQUERY_KEY_B64` igual que `chat_controller.py` y `purchase_orders_controller.py` (#92).
- [ ] En producción, las funciones de este controller que usan BigQuery dejan de mostrar "BigQuery no disponible" cuando las credenciales están correctamente configuradas.

## Context
- Módulo: `chatai/backend/controllers/despacho_controller.py`, función `_get_bq_client()` (línea 61), usada en la sincronización/preview de distribución analítica antes del export (línea ~646).
- Idéntico al bug de #92 (PR #93) — mismo patrón de fix ya aplicado ahí y en `chat_controller.py::init()`.

## Decisions
- Mismo patrón que #92: archivo temporal vía `tempfile.NamedTemporaryFile`, sin extraer helper compartido, para mantener el diff mínimo y consistente con el resto del código.

## Implemented
### Controllers
- `chatai/backend/controllers/despacho_controller.py`

## Routes
No se agregan ni cambian endpoints — mismo comportamiento, credenciales corregidas.

## Tests
Sin suite de tests automatizados para este controller. Verificación manual en Manual QA.

## Manual QA
1. En producción (Cloud Run, con `BIGQUERY_KEY_B64` configurada), ir a la pantalla de Despacho.
2. Abrir el preview de sync de distribución analítica antes del export.
3. Confirmar que ya no aparece "BigQuery no disponible" y que los nombres de CC se resuelven correctamente.

## Deferred
- Ninguno.
