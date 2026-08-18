# Cambiar fórmula de base_trato a prorrateo por horas_trabajadas/horas_trabajar (Zuñiga)
# Path: specs/60-prorated-base-trato-zuniga/spec.md
issue: #60 · branch: 60-prorated-base-trato-zuniga · date: 2026-07-30

## What
Se reemplazó la lógica de `base_trato` del issue #46 ("solo el primer registro de trato del día recibe la base completa") por una regla proporcional aplicada a cada registro individualmente: `base_trato = ROUND(plan.base × horas_trabajadas / plan.horas_trabajar)`, sin importar si hay duplicados el mismo día. Aplicado solo al campo ZUÑIGA (335 filas: 88 Pendiente + 247 Aprobado).

## Acceptance
- [x] Las 335 filas de trato en Zuñiga quedan con los 6 campos derivados recalculados según la fórmula proporcional
- [x] Consistencia interna verificada (`total_trabajado = total_trato`, `total_pagar = total_trabajado + total_contratista`)
- [x] Script SQL versionado
- [x] Test de regresión

## Context
- **Origen del cambio:** el usuario reportó una conversación con otro asistente de IA (extensión de navegador operando sobre el editor de AppSheet) que modificó la fórmula de cálculo para registros *nuevos* de trato. Se pidió replicar el mismo criterio sobre los datos históricos — no se pudo verificar de forma independiente lo hecho en AppSheet, así que se validó todo desde cero contra el esquema real de Postgres antes de tocar producción.
- `appsheet.tarjas_trato` es un catálogo de planes de precio por `id_campo + id_labor + tipo_pago + rango de fechas (fecha_inicio/fecha_fin)`, con columnas `base`, `valor` y `horas_trabajar`. `horas_trabajar` tiene 3 valores reales (9, 7.5, **8**) — la explicación original solo mencionaba 2.
- El JOIN por `id_labor` requiere comparación **numérica**, no de texto — mismo problema de ceros finales que el issue #58 (ej. `'7.20'` ≠ `'7.2'` como texto aunque sean el mismo número). Sin esto, el join fallaba en el 100% de los casos.
- Muchas filas matchean 2-4 planes superpuestos en `tarjas_trato` (distintos niveles de `valor` para la misma labor/fecha), pero se verificó que **`base` y `horas_trabajar` son consistentes al 100%** entre los planes que matchean cada fila — la ambigüedad de `valor` no afecta esta fórmula.
- Se verificó el markup de contratista (~45%) para ambos contratistas de Zuñiga (Multiservicios Bonhomia SPA, Servicios Agrícolas Gutiérrez II SPA) y que `total_jornada`/`contratista_jornada` son 0 en el 100% de estas filas, simplificando la cascada de recálculo.

## Decisions
- **Alcance acotado a Zuñiga por decisión explícita del usuario** — no se aplicó a los demás campos (Isla de Maipo, Talagante, Kontrolag), donde la regla del issue #46 sigue vigente para los registros existentes.
- Este cambio **revierte por completo** el resultado del issue #46 para las filas de Zuñiga (algunas de las 60 filas corregidas ayer están en Zuñiga y ahora vuelven a tener `base_trato > 0`, prorrateado). Se mostró una vista previa concreta al usuario antes de ejecutar, incluyendo ejemplos de esas mismas filas, y se confirmó explícitamente proceder.
- Se usó `DISTINCT ON` para tomar un solo plan por fila al construir el CTE de recálculo, dado que se verificó que `base`/`horas_trabajar` son idénticos entre todos los planes que matchean — cualquiera de ellos da el mismo resultado.
- Impacto neto: `total_pagar` de las 335 filas bajó de \$13.125.152 a \$13.020.353 CLP (-\$104.799) — la regla anterior (base completa solo al primer registro del día) pagaba más en promedio que el prorrateo puro.

## Implemented
### SQL
- `sql/tarjas/13_prorated_base_trato_zuniga.sql` — recálculo en cascada de los 6 campos vía CTE + UPDATE. **Ya ejecutado contra `donar_prod`.**

### Tests
- `chatai/tests/test_60_prorated_base_trato_zuniga.py` — 4 tests: `base_trato` coincide con la fórmula proporcional, consistencia interna de los campos derivados, markup ~45%, isolation check (otros campos no tocados)

## Routes
N/A — corrección de datos, sin cambios de código/endpoints.

## Tests
```
pytest tests/test_60_prorated_base_trato_zuniga.py -v
4 passed in 1.55s

pytest tests/ -v
167 passed in 22.53s
```
Cross-farm isolation: ✅ (test_60_cross_campo_isolation_other_campos_untouched)

## Manual QA
1. `SELECT "id_Resumen", base_trato FROM appsheet.tarjas_pagos WHERE "id_Resumen" IN ('6a302cc1','a16f13fc','c9243a96')` → deben mostrar valores prorrateados no-cero (ej. \$11.667, \$4.167, \$10.833), no \$0 como quedaron bajo el issue #46.
2. Confirmar en la pantalla de Odoo/reportes de Zuñiga que los montos totales cuadran con la nueva regla.

## Deferred
- Los demás campos (Isla de Maipo, Talagante, Kontrolag) siguen bajo la regla del issue #46 — pendiente de decisión del usuario sobre si extender este mismo cambio a todo el sistema.
- No se verificó de forma independiente que el cambio de fórmula descrito por el usuario esté realmente guardado y activo en el editor de AppSheet para registros nuevos — solo se validó y aplicó la corrección histórica en Postgres.
