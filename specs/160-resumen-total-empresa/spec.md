# Resumen Detalle operacional: Total Empresa y % sobre Total trabajado
# Path: specs/160-resumen-total-empresa/spec.md
issue: #160 · branch: 160-resumen-total-empresa · date: 2026-09-09

## What

En `/tarjas/detalle` la tabla **Resumen** (web y PDF) deja de usar `total_pagar` (AppSheet lo deja en 0). Se calcula **Total Empresa** con factores de plataforma y el **%** / gráfico sobre **Total trabajado**.

URL reportada: `/tarjas/detalle?fil-from=2026-09-02&fil-to=2026-09-08&fil-contratista=MULTISERVICIOS+BONHOMIA+SPA&fil-empresa=ZUÑIGA`

## Acceptance

- [x] Columnas Resumen (web y PDF, mismo orden): Tipo de pago, Total trabajadores, Recargo, Costo Empresa, Jornadas, %
- [x] Recargo muestra el % que se suma: Al Día **+50 %**, Trato **+45 %**; footer **—** (factores distintos)
- [x] Sin columna **Total a pagar** en el Resumen
- [x] Al Día: Total Empresa = `total_trabajado * 1.50`; Trato: `* 1.45`; otros tipos: factor `1.0`
- [x] Footer Total Empresa = suma de filas (no mezclar factores)
- [x] % = participación sobre Total trabajado; Al Día + Trato = 100% si son las únicas filas; formato `62.4 %`; Total = `100.0 %` o `—` si el total es 0
- [x] Gráfico de torta usa Total trabajado
- [x] Factores en un solo módulo; web y PDF no duplican 1.45 / 1.50
- [x] PDF masivo `/reportes` hereda el cambio
- [x] No se toca facturación, detalle tractorista, ni columnas de la tabla Detalle fila a fila

## Context

- `chatai/backend/tarjas_empresa.py` — constantes y helpers
- `chatai/backend/controllers/tarjas_controller.py` — `_summary_table_html`, `_query_detalle_resumen`, `get_tarjas_detail`, `_build_detalle_html`
- `chatai/frontend/templates/tarjas_detail.html`, `chatai/frontend/static/tarjas_detail.js`
- Tests: `test_detalle_resumen_total_empresa.py`, `test_detalle_operacional_total_trabajado.py`, `test_96_pdf_detalle_resumen_grafico.py`, `test_122_pdf_detalle_sin_grafico.py`

## Decisions

- Una sola fuente de verdad en `tarjas_empresa.py`. El API anota cada fila con `total_empresa` y `pct`; el JS solo renderiza. El PDF llama `annotate_detalle_resumen` dentro de `_summary_table_html`.
- CLP se redondea a entero (`ROUND_HALF_UP`) en `total_empresa()` para que web (`fmtCLP`) y PDF (`_fmt_clp` con `int()`) no divergjan en centavos.
- Footer Total Empresa = suma de montos de fila, no `grand_trabajado * factor` mezclado.
- `%` sobre el Total trabajado de toda la tabla Resumen (incluye Bono/Tractorista si aparecen). Factor 1.0 para esos tipos.
- Excel de este reporte solo vuelca filas Detalle — no se tocó.
- `_summary_table_html(..., total, jornadas)` conserva la aridad; `total` ya no se usa (antes era total_pagar).

## Implemented

- `chatai/backend/tarjas_empresa.py`
- `chatai/backend/controllers/tarjas_controller.py`
- `chatai/frontend/templates/tarjas_detail.html`
- `chatai/frontend/static/tarjas_detail.js`
- `chatai/tests/test_detalle_resumen_total_empresa.py`
- `chatai/tests/test_detalle_operacional_total_trabajado.py`
- `chatai/tests/test_96_pdf_detalle_resumen_grafico.py`
- `chatai/tests/test_122_pdf_detalle_sin_grafico.py`

## Tests

```
cd chatai && .venv/bin/python -m pytest tests/test_detalle_resumen_total_empresa.py tests/test_122_pdf_detalle_sin_grafico.py tests/test_96_pdf_detalle_resumen_grafico.py tests/test_detalle_operacional_total_trabajado.py -v
```

Issue #160: 15 passed, 0 failed · isolation: ✅ (`test_160_campo_isolation`)

Suite pedida: 38 passed. Falla preexistente en `test_96_badge_class_fallback_empty` (Bono ahora tiene `badge-bono` desde #159 / commit de badge Bono; no es de este cambio).

## Manual QA

1. Abrir `/tarjas/detalle?fil-from=2026-09-02&fil-to=2026-09-08&fil-contratista=MULTISERVICIOS+BONHOMIA+SPA&fil-empresa=ZUÑIGA`
2. Resumen: sin Total a pagar; columnas Tipo / Total trabajado / Recargo / Total Empresa / Jornadas / %. Recargo Al Día **+50 %**, Trato **+45 %**. Al Día Total Empresa **$5.012.750**, Trato **$2.926.100**, % **62.3 %** + **37.7 %** = 100%. Footer Costo Empresa **$7.938.850**.
3. El gráfico de torta debe mostrar ambas rebanadas (no 100% Al Día). Descargar PDF y comprobar las mismas columnas y montos.
