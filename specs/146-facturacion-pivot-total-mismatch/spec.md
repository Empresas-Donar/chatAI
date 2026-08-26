# Total distinto entre UI y tabla dinámica del PDF en Orden de Facturación
# Path: specs/146-facturacion-pivot-total-mismatch/spec.md
issue: #146 · branch: 146-facturacion-pivot-total-mismatch · date: 2026-08-26

## What
El PDF de "Orden de Facturación" muestra, en su propia tabla dinámica por trabajador/fecha, un total ("Suma total") distinto al total del encabezado ("Total a Pagar") y al total mostrado en la UI, para el mismo contratista/empresa/rango de fechas.

## Acceptance
- [x] El total de la tabla dinámica del PDF ("Suma total") debe coincidir siempre con el total del encabezado ("Total a Pagar") del mismo PDF, y ambos con el total mostrado en la UI, para el mismo contratista/empresa/rango de fechas.
- [x] La tabla dinámica solo debe incluir registros con `estado = 'Aprobado'`.
- [x] La tabla dinámica debe basarse en el monto facturable (`total_pagar`), no en el monto pagado al trabajador (`total_trabajado`).

## Context
- Módulo: `chatai/backend/controllers/purchase_orders_controller.py`
- Endpoint afectado: `billing_order_pdf` (`GET /api/odoo/facturacion/pdf`), función que genera el PDF "Orden de Facturación"
- El total de encabezado (UI vía `get_purchase_order` / `GET /api/purchase-orders`, y encabezado del PDF) se calcula desde `appsheet.tarjas_reporte`, que ya filtra `WHERE p.estado = 'Aprobado'` y usa la columna `total_pagar` (ver `sql/tarjas/07_fix_numeric_types.sql`, `sql/tarjas/01_views_reporte.sql`)
- El bloque de tabla dinámica (worker × fecha, título "ORDEN DE FACTURACIÓN", fila "Suma total") dentro de `billing_order_pdf` consulta directamente `appsheet.tarjas_pagos` (sin pasar por `tarjas_reporte`), sumando `total_trabajado` y sin filtrar por `estado`
- Comentario de dominio en `sql/tarjas/01_views_reporte.sql`: `total_pagar = total_trabajado + total_contratista (lo que paga la empresa)` — es decir, `total_trabajado` (pago al trabajador) y `total_pagar` (monto facturable/total a pagar por la empresa) son magnitudes distintas por diseño
- `purchase_order_print_pdf` ("Orden de Compra" PDF) no tiene este problema: usa `tarjas_reporte` tanto para el encabezado como para el detalle, por lo que es internamente consistente
- Se descartaron las dos hipótesis iniciales: (1) el PDF se genera en vivo en cada request (no hay caché/snapshot), y (2) `billing_order_pdf` no usa `tarjas_labores` ni `tarjas_reporte_odoo`, por lo que no aplica el fan-out de JOIN corregido en el issue #130

## Decisions
- Se corrige únicamente la query de la tabla dinámica dentro de `billing_order_pdf`: cambia de `SUM(total_trabajado)` sin filtro de estado, a `SUM(total_pagar) WHERE estado = 'Aprobado'`, replicando el mismo criterio de `tarjas_reporte`
- No se modifica `purchase_order_print_pdf` ni `get_purchase_order`: ya son consistentes entre sí (issue #88) y no presentan este bug
- No se crea vista/migración nueva: es un fix de query dentro del controlador, no de esquema

## Implemented
### Controllers
- `chatai/backend/controllers/purchase_orders_controller.py`

### Tests
- `chatai/tests/test_146_facturacion_pivot_total_mismatch.py`

## Routes
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/odoo/facturacion/pdf | Sin cambio de firma; la tabla dinámica ahora usa `total_pagar` filtrado por `estado='Aprobado'` |

## Tests
```
pytest chatai/tests/test_146_facturacion_pivot_total_mismatch.py chatai/tests/test_88_screen_pdf_total_mismatch.py -v
9 passed in 8.19s
```
Cross-farm isolation: ✅ (`test_146_billing_order_pdf_scoped_to_contratista_and_empresa_isolation`)

Verificado además contra producción, dentro de una sola transacción `REPEATABLE READ` (para descartar ruido de escrituras concurrentes) sobre KONTROLAG + MULTISERVICIOS BONHOMIA SPA + 19/08/2026–25/08/2026:
- Encabezado (`tarjas_reporte`): 4.860.000
- Tabla dinámica antes del fix (`total_trabajado`, sin filtro `estado`): 5.100.000 — no coincide
- Tabla dinámica después del fix (`total_pagar`, `estado='Aprobado'`): 4.860.000 — coincide exactamente

## Manual QA
1. Ir a `/odoo/facturacion`, filtrar contratista "MULTISERVICIOS BONHOMIA SPA", empresa "KONTROLAG", rango 19/08/2026–25/08/2026, y anotar el "Total a Pagar" mostrado en pantalla.
2. Descargar el PDF del mismo filtro y verificar que el total del encabezado ("Total a Pagar") coincide con el de la pantalla.
3. En el mismo PDF, verificar que la fila "Suma total" de la tabla dinámica ("ORDEN DE FACTURACIÓN") coincide exactamente con el total del encabezado.

## Deferred
- Ninguno
