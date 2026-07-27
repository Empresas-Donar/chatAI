# Reportes de tarjas caídos: regex de horas_extras/horas_trabajadas incompatible con columnas numeric
# Path: specs/40-fix-horas-regex-numeric/spec.md
issue: #40 · branch: 40-fix-horas-regex-numeric · date: 2026-07-25

## What
`reports_controller.py` seguía usando el casting defensivo con regex (`col ~ '^[0-9]+(\.[0-9]+)?$'`) contra `horas_trabajadas` y `horas_extras`, columnas que el issue #38 ya convirtió a `NUMERIC`. El operador `~` no existe para `numeric` en PostgreSQL, así que el bulk PDF de `/reportes` (secciones `general` y `resumen-horas`) lanzaba `psycopg2.errors.UndefinedFunction` en cada ejecución.

## Acceptance
- [x] Las 3 consultas que referenciaban `horas_trabajadas ~ '...'` u `horas_extras ~ '...'` en `reports_controller.py` dejan de usar el patrón regex
- [x] La query de `_HORAS_EXPR`/`_HORAS_SUM` (usada por `_html_general`) corre sin error contra la BD real
- [x] La query de `_html_resumen_horas` corre sin error y sus totales agregados coinciden con la suma cruda de `horas_extras`
- [x] Test de regresión que ejecuta las consultas afectadas contra la BD real

## Context
- Issue relacionado y ya resuelto: #38 (PR #39, commit `9d1f8a6`) — convirtió `horas_extras`, `rendimiento`, `horas_trabajadas` a `NUMERIC` en `appsheet.tarjas_pagos` y arregló los 11 sitios equivalentes en `tarjas_controller.py`. **No tocó `reports_controller.py`.**
- Reporte original del usuario: sospecha de que registros con hora extra en decimales (ingresados cuando la columna era TEXT) causaban totales a pago erróneos por aproximación. Verificado contra los datos: los 5 registros con `horas_extras` decimal (1.5) existentes calculan `total_hora_extra` correctamente (1.5 × $3.400/hora tarifa fija = $5.100, exacto). La causa real no es una aproximación en los datos ya guardados, sino el regex roto descrito arriba.
- Confirmado en vivo (servidor local contra `donar_prod`): `/api/reportes/bulk-pdf?reports=general,resumen-horas...` devolvía 500 con traza `reports_controller.py:340 → _pdf_header` — pero ese fallo puntual resultó ser un bug preexistente **no relacionado** (`strftime("%-d de %B de %Y")` usa una extensión glibc que no existe en Windows; funciona en Cloud Run/Linux). Se aisló la query SQL real (independiente del render HTML) y se confirmó que fallaba con `operator does not exist: numeric ~ unknown` antes del fix, y devuelve 313 filas sin error después.

## Decisions
- Mismo estilo de fix que #38: `COALESCE(SUM(CASE WHEN col ~ '...' THEN col::numeric ELSE 0 END), 0)` → `COALESCE(SUM(col), 0)` (y equivalente con `NULLIF`), ya que la columna garantiza tipo numérico y no necesita validación defensiva de texto.
- No se tocó el bug de `strftime("%-d ...")` — es un problema de plataforma (Windows vs Linux) preexistente, no introducido ni cubierto por este fix, y no reproduce en producción (Cloud Run/Linux).
- Test file separado (`test_40_fix_reports_regex.py`) en vez de extender `test_38_fix_numeric_types.py`, para mantener cada test scoped a su propio issue/root cause.

## Implemented
### Controllers
- `chatai/backend/controllers/reports_controller.py` — `_HORAS_EXPR`/`_HORAS_SUM` simplificados (líneas 243-244), `_html_resumen_horas` sin regex (línea ~536)

### Tests
- `chatai/tests/test_40_fix_reports_regex.py` — 4 tests: ambas queries corren sin error contra BD real, guard estático contra reintroducir el patrón roto, isolation check

## Routes
No hay endpoints nuevos. Endpoints que dejan de fallar en la porción SQL:
| Method | Path | Nota |
|--------|------|------|
| GET | /api/reportes/bulk-pdf (reports=general) | Query de `_HORAS_EXPR` ya no lanza error SQL |
| GET | /api/reportes/bulk-pdf (reports=resumen-horas) | Query de `_html_resumen_horas` ya no lanza error SQL |

## Tests
```
pytest tests/test_40_fix_reports_regex.py -v
4 passed in 0.59s

pytest tests/ -v
145 passed in 7.09s
```
Cross-farm isolation: ✅ (test_40_cross_table_isolation_tarjas_pagos_only)

## Manual QA
1. Levantar la app localmente contra `donar_prod`, hacer login.
2. `GET /api/tarjas/resumen-horas/filters` → 200 (ya arreglado por #38, verificado que sigue bien).
3. Ejecutar directamente la query de `_HORAS_EXPR`/`_HORAS_SUM` y la de `_html_resumen_horas` contra la BD → ambas devuelven filas sin `UndefinedFunction`.
4. (Fuera de alcance) `GET /api/reportes/bulk-pdf` en Windows local sigue fallando por el bug preexistente de `strftime`, no relacionado — en producción (Linux) no aplica.

## Deferred
- Bug preexistente de `strftime("%-d de %B de %Y")` en `_pdf_header` (reports_controller.py:202) — falla solo en Windows, funciona en producción (Cloud Run/Linux). Reportar como issue aparte si se quiere compatibilidad de desarrollo local en Windows.
