# Aprobar tarjas Pendientes del campo Zuñiga (23-28 julio 2026)
# Path: specs/56-approve-zuniga-tarjas/spec.md
issue: #56 · branch: 56-approve-zuniga-tarjas · date: 2026-07-29

## What
Se cambió `estado` de `Pendiente` a `Aprobado` para las 311 tarjas de `appsheet.tarjas_pagos` del campo ZUÑIGA (23-28 julio 2026, $12.878.657 CLP), a pedido explícito del usuario. Esto era lo que bloqueaba el reporte "Orden de compra" (revisado en una consulta previa) — la vista `tarjas_reporte` solo incluye filas `Aprobado`.

## Acceptance
- [x] Las 311 filas quedan en estado `Aprobado`
- [x] Test de regresión que verifica el conteo antes/después
- [x] Script SQL versionado en `sql/tarjas/11_approve_zuniga_pendientes.sql`

## Context
- Motivado por una consulta previa del usuario: el reporte "Orden de compra" mostraba "Sin resultados" para Multiservicios Bonhomia SPA + Zuñiga porque esas tarjas estaban en `Pendiente`, no `Aprobado` — explicado como comportamiento esperado (no bug), y el usuario pidió aprobar el lote completo.
- Antes de ejecutar se verificó exhaustivamente contra bugs ya conocidos en este mismo dataset (issues #42, #46): sincronización de `total_contratista`, duplicación de `base_trato`, consistencia de `total_trabajado`.

## Decisions
- **Verificación pre-aprobación:** se encontraron 25 filas (0.12% del monto) con 2 patrones menores:
  - 16 filas con el mismo desfase de ~$20 ya documentado (sin resolver) en el issue #42 (rendimiento fraccionario, artefacto de redondeo heredado).
  - 9 filas nuevas con `total_jornada` consistentemente $1.700 más alto que la fórmula conocida — patrón repetido idéntico en las 9, sugiere un cargo/bono real no capturado en el esquema (no corrupción de datos aleatoria).
  - Se presentaron ambos hallazgos al usuario, quien confirmó explícitamente aprobar las 311 filas de todas formas.
- No se modificó ningún monto — solo el campo `estado`. Los 2 patrones quedan documentados para una futura revisión de negocio, igual que el hallazgo original del issue #42.

## Implemented
### SQL
- `sql/tarjas/11_approve_zuniga_pendientes.sql` — 1 UPDATE idempotente. **Ya ejecutado contra `donar_prod`.**

### Tests
- `chatai/tests/test_56_approve_zuniga_tarjas.py` — 3 tests: 0 filas Pendiente restantes en el rango, `tarjas_reporte` ya las expone, isolation check (otros campos sin tocar)

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_56_approve_zuniga_tarjas.py -v
3 passed in 5.49s

pytest tests/ -v
166 passed in 49.78s
```
Cross-farm isolation: ✅ (test_56_cross_campo_isolation_other_campos_untouched)

## Manual QA
1. En "Orden de compra — Tarjas contratistas", consultar Multiservicios Bonhomia SPA + Zuñiga, 22/07-28/07 → ahora debe mostrar resultados (antes "Sin resultados").
2. `SELECT estado, count(*) FROM appsheet.tarjas_pagos WHERE nombre_campo='ZUÑIGA'` → 0 filas en `Pendiente` para el rango 23-28 julio.

## Deferred
- Las 25 filas con patrones menores no explicados (ver Decisions) quedan pendientes de confirmación de negocio — mismo ítem diferido del issue #42, ahora con un patrón adicional (el de +$1.700 en `total_jornada`) que también requiere contexto de negocio para resolver.
