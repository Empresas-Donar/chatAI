# Costo/hora no se calcula cuando las horas se registraron como hora extra
# Path: specs/140-costo-hora-horas-extra/spec.md
issue: #140 · branch: 140-costo-hora-horas-extra · date: 2026-08-26

## What
El reporte Tarjas → Detalle Operacional mostraba "—" en Costo/hora para labores pagadas total o parcialmente como hora extra; ahora suma `horas_trabajadas + horas_extras` para calcularlo.

## Acceptance
- [x] Una labor pagada 100% como hora extra (horas_trabajadas=0, horas_extras>0) muestra un Costo/hora calculado, no "—".
- [x] Una labor con horas regulares (horas_trabajadas>0, horas_extras=0) sigue calculando exactamente igual que antes (sin regresión).
- [x] No se modifica ningún total a pagar (`total_pagar`, `total_labor`, `total_jornada`) ni ningún dato en `appsheet.tarjas_pagos`.

## Context
- Caso real que originó el reporte: contratista HERBI ML SPA, campo ZUÑIGA, 19-25/08/2026, labor "APERTURA /CERRADO TECHOS" (CC 878), trabajadora Maibet Lobo — 3 tarjas con `horas_trabajadas=0` pero `horas_extras=1,2,3` (6 horas extra en total, $30.600 pagados).
- Query afectada: `_query_detalle_rows` en `chatai/backend/controllers/tarjas_controller.py:698-734`, que alimenta tanto la pantalla como el export PDF/Excel de Detalle Operacional.
- Fuente de datos: vista `appsheet.tarjas_reporte` (`sql/tarjas/01_views_reporte.sql`), que hasta ahora solo exponía `horas_trabajadas` (suma por ventana sobre `p.horas_trabajadas`), no `horas_extras`.
- Se investigó primero si el problema era de datos (intentar poner `horas_trabajadas=9` directamente en `appsheet.tarjas_pagos`) — se descartó: un trigger existente (`trg_fix_total_jornada` / función `appsheet.fix_total_jornada_bug()`) recalcula `total_jornada`/`total_pagar` a partir de `valor_jornada * horas_trabajadas + total_hora_extra` al modificar `horas_trabajadas`, lo que duplicó el pago real de esas 3 tarjas. Se revirtió ese cambio de datos antes de este fix. Este fix es puramente de cálculo/visualización, no toca `tarjas_pagos`.
- Solo se corrigió `_query_detalle_rows` (reporte Detalle Operacional). Otros reportes con fórmulas de costo/hora similares (`tarjas_general`, `tarjas_contratista`, `tarjas_hora_ponderada`) no fueron tocados — quedan fuera de alcance de este issue (ver Deferred).

## Decisions
- La vista `tarjas_reporte` no permite insertar columnas en medio del `SELECT` vía `CREATE OR REPLACE VIEW` (Postgres exige que las columnas existentes conserven su posición) — `horas_extras` se agregó al final de la lista de columnas, no junto a `horas_trabajadas`, para evitar `cannot change name of view column`.
- Se optó por sumar `horas_trabajadas + horas_extras` en el denominador (en vez de crear una columna "horas totales" separada) para mantener el diff mínimo — igual patrón que ya usaba la columna existente.

## Implemented
### SQL
- `sql/tarjas/01_views_reporte.sql`: agrega columna `horas_extras` (`COALESCE(SUM(p.horas_extras) OVER (...), 0)`) al final de la vista `appsheet.tarjas_reporte`, misma partición que `horas_trabajadas`.
- `sql/tarjas/22_add_horas_extras_reporte.sql` (nuevo): migración aplicada en la base de datos.

### Backend
- `chatai/backend/controllers/tarjas_controller.py`: `_query_detalle_rows` — el CASE de `costo_hora` ahora usa `SUM(horas_trabajadas) + SUM(horas_extras)` como condición y denominador.

### Tests
- `chatai/tests/test_140_costo_hora_horas_extra.py` (nuevo)

## Routes
Sin cambios de rutas — mismo endpoint `/api/tarjas/detalle` y sus exports PDF/Excel.

## Tests
```
pytest tests/test_140_costo_hora_horas_extra.py tests/ -k tarja -v
29 passed in 8.86s
```
Cross-farm isolation: N/A (este reporte ya filtra explícitamente por contratista/campo vía query params; no se modificó ese scoping).

## Manual QA
1. En Catálogo de Reportes → Tarjas → Detalle Operacional, filtrar Contratista=HERBI ML SPA, Empresa=ZUÑIGA, 19/08/2026-25/08/2026.
2. Verificar que la fila "APERTURA /CERRADO TECHOS" (CC 878) ahora muestra Costo/hora = $5.100 (antes "—"), con Total y Jornadas sin cambios ($30.600 / 3.0).
3. Verificar que otra fila con horas regulares (ej. CC 866 "SUPERVISOR HUERTO") sigue mostrando $4.500/hr igual que antes.
4. Descargar el PDF y Excel del mismo filtro y confirmar que el valor coincide con lo visto en pantalla.

## Deferred
- No se aplicó el mismo criterio (`horas_trabajadas + horas_extras`) a otros reportes con cálculo de costo/hora (`tarjas_general`, `tarjas_contratista`, `tarjas_hora_ponderada`) — se dejó fuera de alcance porque el issue reportado era específicamente sobre Detalle Operacional.
