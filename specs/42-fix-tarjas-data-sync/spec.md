# Corregir datos desincronizados: total_contratista y valor_jornada en tarjas_pagos
# Path: specs/42-fix-tarjas-data-sync/spec.md
issue: #42 · branch: 42-fix-tarjas-data-sync · date: 2026-07-27

## What
Se resincronizó `total_contratista` con sus componentes (`contratista_jornada + contratista_trato`) en 109 filas, y se corrigió un dato de `valor_jornada` mal ingresado en 5 filas de HERBI ML SPA que había propagado un error de $12.000 CLP a `total_trabajado`/`total_pagar` en una de ellas.

**Importante — alcance reducido respecto al plan original:** durante la verificación se descubrieron 50 filas adicionales donde `total_pagar` no reconcilia con `total_trabajado + total_contratista` sin un patrón uniforme (ver Deferred). Esas filas **no se tocaron** — se decidió junto al usuario esperar confirmación del equipo de operaciones sobre la estructura real de cobro de esos contratistas antes de modificar `total_pagar`, que es el campo que sí alimenta los reportes reales.

## Acceptance
- [x] `total_contratista` = `contratista_jornada + contratista_trato` en las 109 filas afectadas
- [x] `valor_jornada` corregido a 3333 en las 5 filas de HERBI ML SPA (26-29 mayo 2026)
- [x] `total_trabajado`/`total_pagar` recalculados en la fila `c32b7713` con la tarifa corregida
- [x] Script SQL de corrección versionado en `sql/tarjas/08_fix_data_sync.sql`
- [x] Test de regresión que verifica que no quedan filas con `total_contratista` desincronizado
- [ ] ~~Corregir las 50 filas con gap en total_pagar~~ — diferido, pendiente de confirmación de negocio (ver Deferred)

## Context
- Tabla: `appsheet.tarjas_pagos`
- Vistas consumidoras: `tarjas_reporte`/`tarjas_reporte_odoo` usan `total_pagar` directamente (no `total_contratista`), por lo que el bug original no afectaba los reportes en producción — pero sí exponía datos incorrectos si se consultaba `total_contratista` directamente (ej. desde el Chat IA, que describe esa columna en su system prompt).
- `total_pagar` **no fue tocado** para las 109 filas del fix principal (excepto `c32b7713`, único caso donde estaba genuinamente mal por la propagación del error de `valor_jornada`) — se verificó fila por fila antes de decidir qué corregir.

## Decisions
- Se ejecutó el script directamente contra `donar_prod` (con verificación antes/después) en vez de solo dejarlo versionado sin aplicar, dado que el usuario pidió explícitamente "hagas los cambios y corrijas los cálculos".
- Al re-verificar tras el fix, se detectó un patrón NO uniforme en 50 filas adicionales (gap fijo de $15.750 en HERBI ML SPA 13-15 julio; contratista completamente ausente de `total_pagar` en ISLACOR y MULTISERVICIOS BONHOMIA Pendiente) que sugiere un tercer componente de costo de contratista no capturado por `contratista_jornada`/`contratista_trato`. Se decidió **no** corregir `total_pagar` para esas filas sin confirmación de negocio — un ajuste basado en una fórmula incorrecta arriesgaba introducir un error financiero real en vez de corregir uno existente.
- Caso `7beaf777` (misma fecha/contratista que `c32b7713`, pero con `contratista_jornada/trato = 0`) queda como candidato a fix seguro en un follow-up, ya que no aplica la teoría del "cargo oculto" — es la misma clase de staleness que `c32b7713`. No se corrigió en este PR para respetar la pausa acordada sobre las 50 filas.

## Implemented
### SQL
- `sql/tarjas/08_fix_data_sync.sql` — 3 UPDATE idempotentes: resync `total_contratista`, corrección de `valor_jornada` (HERBI ML SPA), recálculo de `total_trabajado`/`total_pagar` en `c32b7713`. **Ya ejecutado contra `donar_prod`.**

### Tests
- `chatai/tests/test_42_fix_tarjas_data_sync.py` — 5 tests: sync de `total_contratista`, `valor_jornada` corregido, `c32b7713` recalculado, isolation check, guard documentando el gap diferido

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_42_fix_tarjas_data_sync.py -v
5 passed in 1.11s

pytest tests/ -v
146 passed in 9.63s
```
Cross-farm isolation: ✅ (test_42_cross_table_isolation_only_tarjas_pagos_touched)

## Manual QA
1. `SELECT count(*) FROM appsheet.tarjas_pagos WHERE ABS(total_contratista - (COALESCE(contratista_jornada,0)+COALESCE(contratista_trato,0))) > 1` → debe devolver 0.
2. `SELECT valor_jornada FROM appsheet.tarjas_pagos WHERE "id_Resumen" IN ('7beaf777','c32b7713','211788c0','a8a6a30a','7eb3e678')` → todos 3333.
3. `SELECT total_trabajado, total_pagar FROM appsheet.tarjas_pagos WHERE "id_Resumen"='c32b7713'` → ambos 30000.

## Deferred
- **50 filas con gap no explicado en `total_pagar`** (HERBI ML SPA 13-15 julio: gap fijo de $15.750; SERVICIOS AGRICOLAS ISLACOR LIMITDA: contratista ausente de `total_pagar`; MULTISERVICIOS BONHOMIA SPA, 15 filas Pendiente: mismo patrón que ISLACOR). Requiere que el equipo de operaciones confirme la estructura de cobro real de estos contratistas (¿cargo fijo de maquinaria/flete aparte del markup por trato?) antes de tocar `total_pagar`. Documentado en el comentario del issue #42.
- `7beaf777` — candidato a fix aislado y seguro (mismo patrón que `c32b7713` pero sin componente de contratista involucrado), no aplicado en este PR por estar dentro del rango de las 50 filas pausadas.
