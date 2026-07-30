# Corregir total_jornada calculado con horas_extras redondeadas hacia arriba
# Path: specs/62-fix-jornada-ceil-horas-extras/spec.md
issue: #62 · branch: 62-fix-jornada-ceil-horas-extras · date: 2026-07-30

## What
12 registros "Al día" (campo ZUÑIGA, contratistas HERBI ML SPA y MULTISERVICIOS BONHOMIA SPA, 23-29 julio 2026) tenían `total_jornada` calculado usando `horas_extras` redondeado hacia arriba (CEIL) en vez del valor decimal real, aunque los campos `horas_extras` y `total_hora_extra` en sí ya estaban correctos.

## Acceptance
- [x] Las 12 filas quedan con `total_jornada = valor_jornada×horas_trabajadas + total_hora_extra`
- [x] `total_trabajado`, `contratista_jornada`, `total_contratista` y `total_pagar` recalculados en cascada
- [x] Script SQL versionado
- [x] Test de regresión

## Context
- Reportado con un caso real de nómina: Rodolfo Henríquez Ahumada, 29 julio — trabajó 9 horas divididas en 2 tarjas (7h en un CC + 2h en otro) más 1.5h extra. Debía ganar $27.000 (9h × $3.000, jornada completa) + $5.100 (1.5h × $3.400 extra) = $32.100, pero el sistema calculaba $33.800 en la fila de 7h (usaba 2h extra → $6.800 en vez de $5.100 → $27.800, + $6.000 de la fila de 2h = $33.800).
- Se investigó primero un reporte más vago del usuario ("nuevamente está aproximando horas extras") que llevó a descartar dos falsos sospechosos: el campo `total_hora_extra` en sí (perfecto, 0 discrepancias en toda la tabla) y un ruido de redondeo de $3 no relacionado (`valor_jornada` almacenado como entero aproximando una tasa con decimal periódico, ya conocido y sin impacto real).
- El caso concreto de Rodolfo permitió aislar la causa raíz real: comparando `total_jornada` contra `valor_jornada×horas + CEIL(horas_extras)×3400`, 12 de 13 filas sospechosas coincidían exactamente con esa fórmula "con redondeo hacia arriba".
- No se encontró este comportamiento en el código de este repositorio — el origen es la fórmula usada en AppSheet al momento de ingresar el dato (fuera del alcance de este repo, sin acceso directo). Este issue corrige solo los datos históricos ya afectados en PostgreSQL.

## Decisions
- Fórmula de corrección: `total_jornada = valor_jornada × horas_trabajadas + total_hora_extra`, reutilizando el `total_hora_extra` ya correcto en vez de recalcular desde `horas_extras` — evita reintroducir cualquier variante del mismo problema.
- Markup de `contratista_jornada` verificado en 50% (distinto al 45% de trato, confirmado por separado) para ambos contratistas afectados antes de aplicar.
- Verificado que `total_trato`/`contratista_trato` son 0 en las 12 filas (pagos "Al día" puros), simplificando la cascada.
- El alcance (12 filas, todas en Zuñiga) surgió naturalmente de la búsqueda por el patrón exacto — no fue necesario acotar manualmente como en el issue #60.

## Implemented
### SQL
- `sql/tarjas/14_fix_jornada_ceil_horas_extras.sql` — CTE + UPDATE, recalcula 5 campos en cascada. **Ya ejecutado contra `donar_prod`.**

### Tests
- `chatai/tests/test_62_fix_jornada_ceil_horas_extras.py` — 5 tests: fórmula `total_jornada` correcta, caso específico de Rodolfo (día completo = $32.100), markup 50%, `total_hora_extra` sin alterar, isolation check (otros campos sin el patrón)

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_62_fix_jornada_ceil_horas_extras.py -v
5 passed in 1.77s

pytest tests/ -v
182 passed, 2 failed (preexistentes de issue #50, no relacionados — ver Deferred)
```
Cross-farm isolation: ✅ (test_62_cross_campo_isolation_only_zuniga_affected)

## Manual QA
1. `SELECT total_jornada, total_pagar FROM appsheet.tarjas_pagos WHERE "id_Resumen"='310c0ca1'` → 26100, 39150.
2. Sumar con la fila hermana del mismo día (`60eef862`, 2h, sin cambios): 26100+6000=32100 = $27.000 jornada completa + $5.100 hora extra.
3. Confirmar con el reporte de nómina real de Rodolfo Henríquez del 29 de julio que el monto ahora coincide.

## Deferred
- `test_50_odoo_export_tractorista.py` tiene 2 tests fallando en `main` (feature de otro issue, mergeada en paralelo) — no relacionado con este fix, no se tocó.
- No se pudo verificar ni corregir la fórmula original en AppSheet (sin acceso) — si el problema persiste para registros *nuevos*, seguirá generando esta misma discrepancia hasta que se corrija en el editor de AppSheet.
