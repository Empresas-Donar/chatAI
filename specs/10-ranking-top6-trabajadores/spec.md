# Spec: Reporte /tarjas/general muestra todos los trabajadores en lugar del top 6

**Issue:** #10
**Branch:** `10-ranking-top6-trabajadores`

## What

La tabla "Ranking por persona" en `/tarjas/general` muestra todos los trabajadores del período
sin límite. El usuario espera ver solo los **top 6 por total ganado**, alineado con el gráfico
de barras que ya usa `LIMIT 6` mediante un CTE `top_workers`.

## Acceptance Criteria

- [ ] La tabla "Ranking por persona" nunca muestra más de 6 filas.
- [ ] El orden es descendente por `SUM(total_trabajado)`.
- [ ] El título de la sección dice "Top 6 — Ranking por persona".
- [ ] El Excel de descarga no se ve afectado (sigue exportando todos los trabajadores).
- [ ] El gráfico de barras no se ve afectado.

## Context

### Root cause

En `GET /api/tarjas/general` (tarjas_controller.py, query #2 "Person ranking"):

```sql
SELECT trabajador, contratista, ...
FROM appsheet.tarjas_pagos
{where}
GROUP BY trabajador, contratista
ORDER BY total DESC
-- sin LIMIT
```

La query no tiene `LIMIT`. El frontend `renderRanking()` en `tarjas_general.js` renderiza
todas las filas recibidas sin filtrar.

El gráfico (query #3) sí limita correctamente via CTE con `LIMIT 6`. La corrección
más robusta es agregar `LIMIT 6` en el backend para que la API ya entregue solo 6 filas,
y actualizar el título en la plantilla HTML.

### Archivos involucrados

- `chatai/backend/controllers/tarjas_controller.py` — query `person_ranking` (línea ~394): agregar `LIMIT 6`
- `chatai/frontend/templates/tarjas_general.html` — título de la sección ranking

## Decisions

- La limitación a top 6 se aplica en el backend (query SQL con `LIMIT 6`), no en el frontend.
  Esto evita que el frontend reciba datos innecesarios y garantiza coherencia entre la tabla y el gráfico.
- El Excel de descarga usa un endpoint separado (`/api/tarjas/general/download-excel`) que hace
  un `SELECT` distinto sin `LIMIT`, por lo que no se ve afectado.
- El título "Top 6 — Ranking por persona" se actualiza en el HTML template para comunicar
  claramente el criterio al usuario.

## Implemented

- `chatai/backend/controllers/tarjas_controller.py` — agregar `LIMIT 6` en query `person_ranking` de `get_tarjas_general`; actualizar comentario a "top 6 earners"
- `chatai/frontend/templates/tarjas_general.html` — título de la sección ranking: "Top 6 — Ranking por persona"

## Tests

5 passed, 0 failed · isolation: N/A (sin cruces entre farms en este endpoint)

- `TestPersonRankingLimit::test_10_ranking_top6_regression` — verifica que LIMIT 6 está presente en la sección `person_ranking`
- `TestPersonRankingLimit::test_limit_value_is_exactly_6` — verifica que el valor del LIMIT es exactamente 6
- `TestPersonRankingLimit::test_chart_cte_also_limits_to_6` — regression guard para el CTE `top_workers` del gráfico
- `TestRankingHtmlTitle::test_ranking_title_includes_top6` — verifica que el HTML incluye "Top 6"
- `TestRankingHtmlTitle::test_ranking_title_includes_ranking_label` — verifica que se mantiene "Ranking por persona"

## Manual QA

1. Abrir `http://localhost:8000/tarjas/general`, seleccionar un rango de fechas con muchos trabajadores (ej. 2026-07-01 a 2026-07-21) y hacer clic en "Consultar".
2. Verificar que la tabla "Top 6 — Ranking por persona" muestra exactamente 6 filas (o menos si hay menos de 6 trabajadores en el período), ordenadas de mayor a menor por la columna "Total".
3. Verificar que el gráfico de barras sigue funcionando con los mismos 6 trabajadores.
4. Descargar el Excel y verificar que contiene TODOS los trabajadores del período (no solo top 6).
