# Agregar columna Máquina en PDF de detalle tractorista
# Path: specs/71-add-maquina-column-pdf/spec.md
issue: #71 · branch: 71-add-maquina-column-pdf · date: 2026-07-31

## What
La tabla plana (fecha → trabajador → labor) del PDF de `/odoo/tarjas-tractorista` ahora incluye una columna "Máquina" a la derecha de "Labor", con el dato de `appsheet.tarjas_pagos.maquina`. Además, se eliminaron las filas "Subtotal {fecha}" por pedido explícito del usuario — solo queda la fila de TOTAL general.

## Acceptance
- [x] La tabla del PDF muestra una columna "Máquina" a la derecha de Labor
- [x] Para filas sin máquina (ej. "OPERARIO SOLO"), la columna se muestra con "–", no rompe el layout
- [x] Anchos de columna se reajustan para que la fecha no vuelva a superponerse (issue #69)
- [x] Se eliminaron las filas de subtotal por fecha (pedido explícito del usuario durante la implementación, fuera del alcance original del issue)
- [x] Test de regresión

## Context
- Columna fuente: `appsheet.tarjas_pagos.maquina` (ya se usaba en `_fetch_tractorista_pivot_rows`/`pivot-excel`/`preview`, pero no en `download-pdf`).
- Verificado: cada combinación (fecha, trabajador, labor) tiene un único valor de `maquina` consistente (un trabajador usa siempre la misma máquina para una labor dada) — agregar `maquina` al `GROUP BY` no fragmenta filas existentes.
- La tabla "por operador" (issue #67) no se tocó — no necesita esta columna (agrupa por trabajador — labor, sin desglose de máquina).

## Decisions
- Anchos de columna reajustados de 12/30/33/25% (issue #69) a 10/24/26/20/20% (Fecha/Trabajador/Labor/Máquina/Total) para dar espacio a la columna nueva — se actualizó `test_69_fix_blurry_date_pdf.py` para reflejar los nuevos porcentajes (mismo principio de `table-layout:fixed`, solo cambian los valores).
- Filas sin máquina (`maquina IS NULL`, ej. "OPERARIO SOLO") muestran "–" en vez de una celda vacía, para que se note que es intencional y no un dato faltante.
- Se eliminaron las filas "Subtotal {fecha}" — pedido explícito del usuario durante la implementación ("quiero que además saques las filas que dicen subtotal de cada fecha"), no estaba en el acceptance original del issue pero se incorporó al mismo cambio ya que toca el mismo bloque de código.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py` — `download_tarjas_tractorista_pdf`:
  - Query: se agregó `maquina` al `SELECT` y `GROUP BY`.
  - Se agregó el `<th>`/`<td>` de Máquina con fallback `"–"` cuando es `None`.
  - Se eliminaron las filas de subtotal por fecha; solo queda la fila TOTAL (ahora con `colspan="4"`).
  - Anchos de columna reajustados a 10/24/26/20/20%.

### Tests
- `chatai/tests/test_71_maquina_column_pdf.py` — 5 tests: columna Máquina presente en el header/celdas, filas de subtotal ausentes, query incluye `maquina` en el `GROUP BY`, el PDF sigue renderizando, filas sin máquina (`OPERARIO SOLO`) no rompen la query y conviven con filas que sí tienen máquina.
- `chatai/tests/test_69_fix_blurry_date_pdf.py` — actualizado para los nuevos porcentajes de ancho (10/24/26/20/20 en vez de 12/30/33/25).

## Routes
N/A — mismo endpoint existente (`GET /api/tarjas/tractorista/download-pdf`), sin cambio de contrato de query params.

## Tests
```
pytest tests/test_71_maquina_column_pdf.py tests/test_69_fix_blurry_date_pdf.py tests/test_67_pivot_table_screen_pdf.py -v
16 passed in 6.39s

pytest tests/ -v
193 passed, 2 failed in 18.74s
```
Los 2 fallos (`test_50_odoo_export_tractorista.py`) son preexistentes en `main`, no relacionados con este fix.

Cross-farm isolation: N/A — cambio de columnas/layout en un reporte, no toca scoping de datos.

## Manual QA
1. En `/odoo/tarjas-tractorista`, generar una orden y descargar el PDF → debe verse la columna "Máquina" entre Labor y Total a pagar, con el nombre de la máquina para "Jornada Tractor normal/simple" y "–" para "OPERARIO SOLO".
2. Confirmar que ya no aparecen filas "Subtotal {fecha}" — solo la fila TOTAL al final.
3. Confirmar que la fecha sigue sin superponerse con el resto de columnas (issue #69 no regresionó).
