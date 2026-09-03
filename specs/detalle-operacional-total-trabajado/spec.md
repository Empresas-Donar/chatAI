# Detalle operacional: columna Total trabajado
# Path: specs/detalle-operacional-total-trabajado/spec.md
branch: detalle-columna-total-trabajado · date: 2026-09-02

## What

En `/tarjas/detalle` (HERBI ML SPA · TALAGANTE · 26/08–01/09/2026) el usuario ve **$1.131.000** (Total a pagar) y espera ver también **$2.219.000**. Se agrega la columna **Total trabajado** sin reemplazar Total a pagar / Costo total.

## Criterios de aceptación

- [x] Resumen, detalle, Excel y PDF muestran la columna **Total trabajado**
- [x] Con esos filtros, Total a pagar / Costo total sigue en **$1.131.000** (`total_pagar`)
- [x] Total trabajado suma **$2.219.000** (`SUM(total_trabajado)` Aprobado)
- [x] El gráfico de torta sigue usando Total a pagar
- [x] Filtro por empresa no mezcla Talagante con Isla de Maipo

## Contexto

- `total_pagar` llega en 0 desde ~28/08 (AppSheet); `total_trabajado` sí viene lleno
- Total a pagar = lo facturable a la empresa cuando AppSheet lo calcula (`trabajado + comisión`)
- Total trabajado = pago a la cuadrilla, mismo criterio que `/tarjas/general`

## Decisiones

- Consultar `tarjas_pagos` (Aprobado) para poder leer ambas columnas. `tarjas_reporte` no expone `total_trabajado`.
- Costo por hora, unitario y % del pago siguen sobre `total_pagar` para no cambiar el significado de esas columnas.
- PDF masivo `/reportes` hereda el cambio vía `_build_detalle_html`.

## Implementado

- `chatai/backend/controllers/tarjas_controller.py`
- `chatai/frontend/templates/tarjas_detail.html`
- `chatai/frontend/static/tarjas_detail.js`
- `chatai/tests/test_detalle_operacional_total_trabajado.py`
- `chatai/tests/test_152_detalle_tractorista_pendiente.py`
- `chatai/tests/test_153_detalle_tractorista_pivote.py`

## QA Manual

1. Abrir `/tarjas/detalle?fil-from=2026-08-26&fil-to=2026-09-01&fil-contratista=HERBI+ML+SPA&fil-empresa=TALAGANTE`
2. Resumen: Total a pagar **$1.131.000**, Total trabajado **$2.219.000**
3. En Detalle, la fila **Total** al pie suma jornadas, Costo total ($1.131.000) y Total trabajado ($2.219.000)
4. Excel y PDF del mismo filtro incluyen la columna y la fila Total
