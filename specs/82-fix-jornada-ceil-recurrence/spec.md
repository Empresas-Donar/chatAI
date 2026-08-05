# Recurrencia: total_jornada con horas_extras redondeadas (CEIL)
# Path: specs/82-fix-jornada-ceil-recurrence/spec.md
issue: #82 · branch: 82-fix-jornada-ceil-recurrence · date: 2026-08-05

## What
4 filas (Cristian González Dinamarca / MULTISERVICIOS BONHOMIA SPA y Maibet Lobo / HERBI ML SPA, 3-4 agosto 2026) tenían `total_jornada` mal calculado por el mismo bug de #62 (redondeo CEIL o hora extra omitida del todo); se corrigen los datos y se agrega un trigger que autocorrija esta discrepancia en cada INSERT/UPDATE futuro.

## Acceptance
- [x] Las filas afectadas quedan con `total_jornada = valor_jornada×horas_trabajadas + total_hora_extra`
- [x] `total_trabajado` y `total_pagar` recalculados en cascada (`contratista_jornada`/`total_contratista` no se tocan — ya estaban correctos)
- [x] Salvaguarda permanente: trigger en PostgreSQL que recalcula `total_jornada` en cada INSERT/UPDATE cuando la discrepancia es significativa (>$500)
- [x] Test de regresión

## Context
- Módulo: sin código Python involucrado — bug 100% en datos (`appsheet.tarjas_pagos`), origen en AppSheet (fuera del repo)
- Precedente exacto: issue #62 / PR #63 (`sql/tarjas/14_fix_jornada_ceil_horas_extras.sql`, rama `62-fix-jornada-ceil-horas-extras`, no mergeada a `main` pero ya ejecutada contra `donar_prod`) — corrigió 12 filas históricas (23-29 julio) con el mismo patrón, sin agregar salvaguarda permanente. El propio PR advertía que reaparecería en registros nuevos.
- Patrón de trigger existente a seguir: `sql/tarjas/05_trigger_id_labor.sql` (`CREATE OR REPLACE FUNCTION appsheet.<fn>() ... BEFORE INSERT OR UPDATE OF <cols> ON appsheet.tarjas_pagos`)
- **`appsheet.tarjas_pagos` es una tabla viva**: AppSheet sincroniza filas nuevas continuamente (confirmado durante este fix — aparecieron filas nuevas entre un barrido y el siguiente). El alcance de este issue creció de 2 a 4 filas en el proceso: el barrido inicial (umbral >$500 sobre las 727 filas "Al día") solo encontró las 2 de Cristian González; correr el mismo barrido de nuevo como test de regresión, ya con esas 2 corregidas, encontró 2 filas más (Maibet Lobo) que no existían o no tenían el bug en el primer barrido.
- Filas afectadas:
  - `id_Resumen='eb9f5d80'` (Cristian González Dinamarca, MULTISERVICIOS BONHOMIA SPA, 3 agosto) — variante CEIL: `total_jornada` usaba `CEIL(horas_extras)` en vez del valor real
  - `id_Resumen='7e0da2e5'` — duplicado exacto de `eb9f5d80` (mismo trabajo, `id_tarja_supervisor` distinto), tenía el mismo bug y se corrigió igual, pero **desapareció de la tabla por sí solo** entre la corrección y la finalización de los tests (sync/dedup externo, no causado por este fix) — ya no existe, no se sigue rastreando
  - `id_Resumen='cb9a21d3'`, `'034056fd'` (Maibet Lobo, HERBI ML SPA, 4 y 3 agosto) — variante omisión: `total_jornada=0` pese a `total_hora_extra=1700`, la hora extra no se sumó en absoluto (mismo patrón ya visto una vez en #62 para `id_Resumen='c874eed9'`)

## Decisions
- **No se toca la duplicación de tarjas** (`eb9f5d80`/`7e0da2e5` son filas idénticas con distinto `id_tarja_supervisor`) — es un hallazgo separado, no relacionado al cálculo de hora extra, y borrar una fila de pago requiere confirmación explícita del usuario antes de tocarlo.
- Fórmula de corrección igual a #62: `total_jornada = valor_jornada × horas_trabajadas + total_hora_extra` (reutiliza `total_hora_extra`, ya correcto).
- `contratista_jornada`/`total_contratista` **no se recalculan** — a diferencia de #62, en estas 2 filas ya estaban correctos (9.350 = 50% de 18.700, el valor correcto), calculados por AppSheet de forma independiente al campo `total_jornada` roto. Recalcularlos igual habría sido inofensivo pero innecesario.
- El trigger usa un **umbral de $500** (no corrige cualquier diferencia) porque un barrido completo de las 727 filas `Al día` mostró ruido de redondeo inofensivo de $1–3 (valor_jornada almacenado como decimal periódico aproximado, ya documentado y aceptado en #62) en ~224 filas. Un trigger sin umbral sobrescribiría ese ruido histórico en cada UPDATE futuro sin necesidad. $500 está muy por debajo del bug real (mínimo $1.700 = 1 hora extra completa × $3.400) y muy por encima del ruido de redondeo.
- El trigger dispara en INSERT y UPDATE de las columnas relevantes (`valor_jornada`, `horas_trabajadas`, `total_hora_extra`, `tipo_pago`) para cubrir tanto sincronización nueva como reprocesos de filas existentes, igual que el patrón de `05_trigger_id_labor.sql`.
- Alcance: solo filas `tipo_pago` = 'Al dia'/'Al día' — confirmado que en esas filas `total_trato` siempre es 0 (727/727), así que la fórmula no necesita considerar el componente de trato.

## Implemented
### SQL
- `sql/tarjas/20_fix_jornada_ceil_cristian_gonzalez.sql` — UPDATE puntual de las 2 filas de Cristian González (dato)
- `sql/tarjas/21_trigger_fix_total_jornada.sql` — trigger `trg_fix_total_jornada` / función `appsheet.fix_total_jornada_bug()` (salvaguarda permanente)
- `sql/tarjas/22_fix_jornada_omitted_maibet_lobo.sql` — UPDATE puntual de las 2 filas de Maibet Lobo, encontradas por el barrido de regresión después de aplicar los 2 scripts anteriores

### Tests
- `chatai/tests/test_82_fix_jornada_ceil_recurrence.py`

## Routes
N/A — corrección de datos + trigger de integridad, sin cambios de endpoints.

## Tests
```
pytest tests/test_82_fix_jornada_ceil_recurrence.py -v
7 passed in 14.94s

pytest tests/ -v
205 passed, 2 failed (preexistentes de test_50_odoo_export_tractorista.py, no relacionados — ya documentados como deferred en PR #63)
```
Cross-farm isolation: ✅ (`test_82_cross_contratista_isolation` — solo las filas del alcance de este issue cambiaron; `test_82_full_table_sweep_no_remaining_real_discrepancy` confirma 0 discrepancias reales en toda la tabla)

## Manual QA
1. `SELECT total_jornada, total_trabajado, total_pagar FROM appsheet.tarjas_pagos WHERE "id_Resumen" IN ('eb9f5d80','cb9a21d3','034056fd')` → 18.700/18.700/28.050 y 1.700/1.700/2.550 (x2).
2. Simular una nueva fila con el mismo patrón (`horas_extras` fraccional, `total_jornada` mal calculado con CEIL u omitido) vía INSERT/UPDATE directo → el trigger debe corregirla automáticamente antes de guardar (cubierto por `test_82_trigger_autocorrects_ceil_bug_on_insert`).
3. Confirmar que una diferencia pequeña (ruido de redondeo ~$1-3) NO se sobrescribe (cubierto por `test_82_trigger_ignores_small_rounding_noise`).

## Deferred
- Duplicación de tarja (`eb9f5d80` / `7e0da2e5`, mismo trabajo con dos `id_tarja_supervisor`) — reportado, no corregido en este issue por decisión explícita del usuario. `7e0da2e5` desapareció de la tabla por sí solo durante este trabajo (sync/dedup externo); ya no requiere acción.
- No se puede corregir la fórmula original en AppSheet (sin acceso) — este trigger es una salvaguarda a nivel de base de datos, no elimina la causa raíz en el origen.
- Hallazgo incidental: `appsheet.tarjas_pagos` no tiene constraint PK/UNIQUE en `id_Resumen` a nivel de PostgreSQL (verificado vía `pg_constraint` al depurar un test) pese a que la convención del proyecto (CLAUDE.md) indica `TEXT NOT NULL PRIMARY KEY` para todas las tablas migradas. No se corrige aquí — fuera de alcance, podría ameritar su propio issue.
