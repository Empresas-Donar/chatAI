# Spec: sync_cc — Modelos de Distribución Analítica no se sincronizan a tarjas_cc

**Issue:** #7
**Branch:** `7-sync-distribucion-analitica`

---

## What

`apps/sync_cc.py` solo sincroniza CCs individuales desde `CC_analiticos`, ignorando completamente
la tabla `Modelos_Distribucion_Analitica`. Los modelos de distribución (que el operario selecciona
en AppSheet como un "CC virtual" que distribuye costos a múltiples CCs reales) nunca se insertan
en `appsheet.tarjas_cc`.

---

## Acceptance Criteria

- Todos los registros de `Modelos_Distribucion_Analitica` con `x_studio_numeracin` no nulo se
  insertan en `tarjas_cc` usando `x_studio_numeracin` como `id_cc`.
- El campo `valor_odoo` contiene el JSON `analytic_distribution` tal como viene de Odoo.
- El campo `cultivo` se obtiene del nombre del CC correspondiente en `CC_analiticos`
  (lookup por `code = x_studio_numeracin`, con fallback a lookup por `id = analytic_distribution_code_id`,
  y último recurso: el propio `x_studio_numeracin`).
- La sincronización es idempotente (`ON CONFLICT DO NOTHING`).
- Los modelos ya existentes en `tarjas_cc` no se alteran.
- Test de regresión: un modelo de distribución con múltiples CCs aparece correctamente en
  `tarjas_cc` tras la sincronización.

---

## Context

### Archivos involucrados

- `apps/sync_cc.py` — script de sincronización principal
- `chatai/tests/test_sync_cc.py` — suite de tests existente (tests unitarios, sin DB real)

### Estructura de `Modelos_Distribucion_Analitica` (BigQuery)

Campos relevantes:
- `id` — PK del modelo
- `x_studio_numeracin` — código numérico del modelo (es el `id_cc` que va a `tarjas_cc`)
- `analytic_distribution` — JSON string `{"odoo_cc_id": porcentaje, ...}`
- `analytic_distribution_code_id` — FK a `CC_analiticos.id` (para resolver el nombre del cultivo)
- `company_id` — empresa (para resolver `id_campo` vía `COMPANY_TO_CAMPO`)

### Resolución del campo `cultivo`

1. Match por `CC_analiticos.code = x_studio_numeracin` → nombre del CC
2. Fallback: match por `CC_analiticos.id = analytic_distribution_code_id` → nombre del CC
3. Último recurso: usar `x_studio_numeracin` como nombre

### Datos reales en BigQuery (40 modelos, julio 2026)

Los modelos confirmados en el issue (#632–#639, #1500) están presentes.

---

## Decisions

- Se agrega una nueva función `fetch_odoo_distribucion_models(bq)` que retorna
  `list[dict]` con campos `{id_cc, cultivo, id_campo, valor_odoo}` listos para insertar.
- La función `run()` llama `sync_distribucion_models()` en la misma transacción que
  `sync_tarjas_cc()` y `sync_despacho_cc()`.
- El lookup de cultivo se hace en Python sobre el dict `by_code` ya calculado por
  `fetch_odoo_cc()`, para evitar una segunda query a BigQuery. Si no hay match por code,
  se usa `analytic_distribution_code_id` buscando en `by_id` (dict inverso). Último
  recurso: el propio `x_studio_numeracin`.
- `ON CONFLICT (id_cc) DO NOTHING` — nunca se sobreescribe un modelo existente.
- Los modelos sin `x_studio_numeracin` se ignoran con un warning (misma política que
  CCs sin code).

---

## Implemented

- `apps/sync_cc.py` — agrega `fetch_odoo_distribucion_models()` y `sync_distribucion_models()`; actualiza `run()`
- `chatai/tests/test_sync_cc.py` — agrega `TestSyncDistribucionModels` con regression test

---

## Tests

13 passed, 0 failed · isolation: N/A (script-level, not multi-tenant API)

---

## Manual QA

1. Correr `python apps/sync_cc.py` y verificar que el log muestra "modelos distribución →
   insertados: N" con N > 0.
2. En PostgreSQL: `SELECT id_cc, cultivo, valor_odoo FROM appsheet.tarjas_cc WHERE id_cc IN
   ('632','633','634','639','1500') ORDER BY id_cc;` — deben existir las 5 filas.
3. Para el modelo 632: `valor_odoo` debe ser `{"735": 9.6, "736": 90.4}`.
