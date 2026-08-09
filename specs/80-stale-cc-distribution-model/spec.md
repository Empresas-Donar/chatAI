# Distribución analítica (CC) desactualizada en export a Odoo — modelo "Donar 2" con porcentajes obsoletos
# Path: specs/80-stale-cc-distribution-model/spec.md
issue: #80 · branch: 80-stale-cc-distribution-model · date: 2026-08-04

## What
`sync_distribucion_models()` en `apps/sync_cc.py` nunca actualiza `appsheet.tarjas_cc.valor_odoo` para un modelo de distribución analítica ya existente, aunque el modelo se edite después en Odoo — causando que las órdenes de compra exportadas usen porcentajes de CC obsoletos.

## Acceptance
- [x] `sync_distribucion_models()` actualiza `valor_odoo` (y `cultivo`) de los modelos ya existentes cuando el valor en Odoo difiere del guardado, en vez de omitirlos siempre.
- [x] La corrección no toca la lógica de `sync_tarjas_cc()` para CCs individuales (que sí depende intencionalmente de no pisar reemplazos de códigos archivados).
- [x] Se corre el sync corregido y se verifica que `tarjas_cc.valor_odoo` para `id_cc=400` pasa a coincidir con los porcentajes actuales de "Donar 2" en Odoo. Ejecutado contra `donar_prod` el 2026-08-04: `id_cc=400` quedó en `{"398": 12.5, "399": 3.13, "400": 9.37, "401": 12.5, "402": 9.37, "403": 3.13, "724": 12.5, "725": 12.5, "730": 12.5, "731": 12.5}` — coincide con Odoo. Log: `insertados: 0, actualizados: 30, sin cambios: 10` — el bug afectaba a 30/40 modelos, no solo a este caso.
- [x] Test de regresión que reproduce el bug: un modelo ya existente con porcentajes distintos a los de Odoo se actualiza tras correr el sync.

## Context
- Módulo: `apps/sync_cc.py` (script de sincronización BigQuery → PostgreSQL, no es parte de la app FastAPI).
- Tests existentes: `chatai/tests/test_sync_cc.py` (`TestSyncDistribucionModels`, agregada en issue #7).
- Consumidores del dato afectado (vía `LEFT JOIN appsheet.tarjas_cc cc ON cc.id_cc::text = ...`):
  - `sql/tarjas/02_views_odoo.sql` → vista `tarjas_reporte_odoo` (cuadrillas)
  - `sql/tarjas/08_views_odoo_tractorista.sql` → vista `tarjas_reporte_odoo_tractorista` (tractoristas)
- Caso confirmado en producción (solo lectura, sin escritura): `id_cc=400` (cultivo "LAS VERTIENTES" / "Donar 2" en Odoo), usado en el PO `OCD2-00857`. `appsheet.tarjas_cc.valor_odoo` para ese id coincide exactamente con los porcentajes "viejos" exportados, mientras Odoo ya tiene otros. `appsheet.sync_meta.last_cc_sync` muestra que el sync corrió el mismo día sin corregirlo — comportamiento esperado dado el `ON CONFLICT (id_cc) DO NOTHING` actual, documentado explícitamente en el docstring de la función como "never overwrites existing rows".
- `fetch_odoo_distribucion_models()` ya trae el valor correcto y vigente desde `Modelos_Distribucion_Analitica` (BigQuery) en cada corrida — el problema es exclusivamente que `sync_distribucion_models()` descarta ese valor fresco cuando el `id_cc` ya existe.

## Decisions
- Se compara el `valor_odoo` guardado contra el de Odoo como diccionarios ya parseados (no como strings), para no disparar UPDATEs falsos por diferencias de formato/orden de claves en el JSON.
- Se actualiza `cultivo` junto con `valor_odoo` en el mismo UPDATE — si Odoo también renombró el modelo, no tiene sentido refrescar el porcentaje pero dejar el nombre viejo.
- `sync_tarjas_cc()` (CCs individuales) queda intacto: su `ON CONFLICT DO NOTHING` + lógica de reemplazo de IDs archivados protege ediciones manuales hechas desde la app (fix de códigos duplicados). Los modelos de distribución no tienen ese caso de uso — Odoo es la única fuente de verdad — así que ahí sí corresponde reflejar siempre el valor vigente.
- No se ejecutó el sync corregido contra producción en esta sesión: es una escritura real sobre `donar_prod` y se deja como paso de despliegue explícito, separado de la aprobación del código.

## Implemented
### Scripts
- `apps/sync_cc.py` — `sync_distribucion_models()` ahora hace UPDATE de `cultivo`/`valor_odoo` cuando un modelo ya existente difiere del valor vigente en Odoo, además de insertar los nuevos. Docstring del módulo actualizado.

### Tests
- `chatai/tests/test_sync_cc.py` — nueva clase `TestSyncDistribucionModelsWrite` con 3 tests: modelo obsoleto se actualiza (regresión #80), modelo sin cambios no se toca, modelo nuevo se sigue insertando igual que antes.

## Tests
```
pytest tests/test_sync_cc.py -v
16 passed in 0.18s
```
Cross-farm isolation: N/A (script de sincronización a nivel de cuenta, no hay aislamiento por farm en `tarjas_cc`).

## Manual QA
1. Correr `python apps/sync_cc.py` contra producción y verificar en el log la línea `Modelos distribución → insertados: N, actualizados: M, sin cambios: K` con `M >= 1`.
2. En PostgreSQL: `SELECT valor_odoo FROM appsheet.tarjas_cc WHERE id_cc = '400';` — debe mostrar los porcentajes vigentes de Odoo (12.5%, 3.13%, 9.37%, etc.), no los reportados originalmente en el issue.
3. Volver a exportar/objetivo el PO de tractorista para el mismo contratista/campo/rango de fechas y confirmar que la distribución analítica generada coincide con la de Odoo.
4. Confirmar que otros modelos de distribución no afectados (ej. `id_cc=270`) no aparecen en el log como "actualizados" — solo los que realmente cambiaron.

## Deferred
- No se investigó si el modelo de distribución "400" cambió por una edición manual en Odoo o por un proceso automático (fuera del alcance de este fix, que corrige la sincronización, no audita el cambio de origen).
