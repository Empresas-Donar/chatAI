# tarjas_cc no se resincroniza automáticamente con Odoo, exportando Centros de Costo archivados
# Path: specs/126-auto-sync-cc-archivados/spec.md
issue: #126 · branch: 126-auto-sync-cc-archivados · date: 2026-08-19

## What
`sync_distribucion_models` (parte de `apps/sync_cc.py`, corrido cada 5h vía GitHub Actions) nunca actualizaba una fila `tarjas_cc` ya existente, así que un Centro de Costo archivado en Odoo se quedaba pegado en `valor_odoo` indefinidamente hasta que alguien lo notara y corrigiera a mano.

## Acceptance
<!-- Copiado del issue #126 -->
- [x] `tarjas_cc` se resincroniza automáticamente contra los CC activos de Odoo (BigQuery) cada vez que corre el sync (cada 5h), igual que ya ocurre con las labores (`_sync_labores`) en cada export.
- [x] El fallo de BigQuery al sincronizar no rompe el resto del sync (ya era así: `run()` hace rollback y re-lanza, el cron reintenta en la próxima corrida — sin cambios en ese comportamiento).
- [x] Test de regresión que reproduzca el bug (CC archivado en `tarjas_cc` se reemplaza tras correr `sync_distribucion_models`).

## Context
- `apps/sync_cc.py` corre cada 5h vía `.github/workflows/sync_cc.yml` (`cron: '0 */5 * * *'`) — confirmado con `gh run list` que el workflow corre exitosamente, así que el bug no era que el cron fallara, sino que su lógica de sync explícitamente omitía filas existentes.
- `sync_tarjas_cc` (CC individuales de `CC_analiticos`) ya reemplazaba IDs archivados por su equivalente activo vía `archived_to_replacements` (fuzzy match por código o por nombre/plan) — pero solo resuelve los casos con un reemplazo confiable (ej. issue reportado: 4 de 23 IDs archivados tenían reemplazo automático).
- `sync_distribucion_models` (modelos de `Modelos_Distribucion_Analitica`, ej. `id_cc="210"`) usaba `INSERT ... ON CONFLICT (id_cc) DO NOTHING` — documentado explícitamente como "never overwrites existing rows". Si el modelo en Odoo cambiaba (CC archivados, redistribución de %), la fila ya existente en `tarjas_cc` nunca se refrescaba.
- Caso real (esta semana, HERBI ML SPA / TALAGANTE, 12–18/08/2026): `tarjas_cc.id_cc='210'` tenía 23 CC archivados de la temporada 25/26 (pimientos "MT-25/26 PIM.ROJO", etc.) en su `valor_odoo`, sin que el sync los corrigiera.

## Decisions
- El fix es puntual: `sync_distribucion_models` ahora recibe `active_ids` y, para un `id_cc` que ya existe, compara sus keys almacenadas contra `active_ids`; si alguna está archivada, sobreescribe `valor_odoo` completo con la distribución vigente del modelo en Odoo (fuente de verdad). Si ninguna key está archivada, la fila se deja intacta — para no pisar ediciones manuales que no involucren un CC archivado.
- No se tocó `sync_tarjas_cc` (su lógica de reemplazo por fuzzy-match ya era correcta y se mantiene como primera línea de defensa para CC individuales).
- Se descartó agregar un sync duplicado en `purchase_orders_controller.py` (a nivel de request, antes de cada export) — habría sido una segunda implementación paralela del mismo algoritmo que ya corre cada 5h vía cron; el fix de raíz en `apps/sync_cc.py` cierra el problema sin duplicar lógica.
- Corrección inmediata de datos en producción (fuera de este PR, aplicada directamente vía SQL antes del fix de código): `tarjas_cc.id_cc='210'` actualizado con la distribución vigente entregada por el usuario (sin CC archivados, incluye el nuevo CC 759); `tarjas_cc.id_cc='583'` eliminado (superseded por `id_cc='639'`, que ya existía con la distribución correcta y no tenía ninguna fila de `tarjas_pagos` apuntándole).

## Implemented
### Scripts
- `apps/sync_cc.py` — `sync_distribucion_models` ahora refresca filas existentes con CC archivados; `run()` pasa `active_ids`.

### Tests
- `chatai/tests/test_sync_cc.py` — `TestSyncDistribucionModelsRefresh` (4 tests).

## Tests
```
pytest chatai/tests/test_sync_cc.py -v
36 passed in 0.30s
```
Cross-farm isolation: no aplica (tabla de catálogo compartida, sin dimensión de campo en esta prueba) — ✅ ya cubierto por las suites existentes de `_resolve_campo` / `ALLOWED_COMPANY_IDS`.

## Manual QA
1. `gh workflow run sync_cc.yml` y verificar en los logs `Modelos distribución → ... refrescados (archivados detectados): N` con N > 0 si queda algún `id_cc` con CC archivado.
2. Volver a introducir manualmente un CC archivado en un `valor_odoo` de prueba, correr `python apps/sync_cc.py` localmente, y confirmar que la fila se sobreescribe con la distribución vigente del modelo.
3. Confirmar que una fila sin CC archivados no cambia su `updated_at`/`valor_odoo` tras correr el sync dos veces seguidas.

## Deferred
- Los 19 CC archivados sin reemplazo automático (fuera del caso ya corregido a mano) siguen requiriendo que alguien en Odoo defina el CC vigente para cada uno — es una decisión de negocio, no de código.
