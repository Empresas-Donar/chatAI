# Orden de Facturación: pago al trabajador y comisión
# Path: specs/157-facturacion-trabajador-comision/spec.md
issue: facturación trabajador vs comisión · date: 2026-09-03

## What
En `/odoo/facturacion` (HERBI ML SPA / KONTROLAG / 26/08–01/09/2026) cada celda del pivot y el "Total a Pagar" muestran el monto **ya con comisión** (`total_pagar`). El contratista no puede ver cuánto va al trabajador y cuánto es su comisión.

URL: http://localhost:8000/odoo/facturacion?inp-date-from=2026-08-26&inp-date-to=2026-09-01&sel-contractor=HERBI+ML+SPA&sel-company=KONTROLAG

## Acceptance
- [x] El encabezado GLOSA muestra **Total trabajadores**, **Adicional** y **Total a Pagar** (además de Total a Trato y Total Al Día)
- [x] Cada celda día muestra **solo** el pago al trabajador (`total_trabajado`)
- [x] Debajo de la tabla: **Subtotal** (trabajadores) + **Adicional** + **Total**
- [x] Para HERBI ML SPA / KONTROLAG / 26/08–01/09/2026: subtotal **$175.000**, comisión **$87.500**, total **$262.500**
- [x] El PDF (`GET /api/odoo/facturacion/pdf`) muestra el mismo desglose
- [x] El reporte operativo `/tarjas/contratista` no se modifica

## Context
- Fórmula de dominio: `total_pagar = total_trabajado + total_contratista`
- Tras #156 el pivot ya usa el monto facturable (con fallback si `total_pagar` es 0). Eso corrigió el $0 vs $175.000, pero dejó de mostrar el pago al trabajador
- `total_trabajado` = lo que cobra la cuadrilla; `total_contratista` = comisión del contratista; `total_pagar` = lo que factura la empresa

## Decisions
- No se reemplaza el total facturable: se **agrega** el desglose. Total a Pagar sigue siendo `COALESCE(NULLIF(total_pagar, 0), total_trabajado + total_contratista)`
- Pantalla y PDF siguen compartiendo `_fetch_billing_order`; las columnas nuevas se agregan al final del tuple para no romper tests que leen `r[2]` como monto facturable
- En la tabla: solo pago al trabajador. Debajo: Subtotal + Adicional + Total

## Implemented
- `chatai/backend/controllers/purchase_orders_controller.py`
- `chatai/frontend/static/billing_order.js`
- `chatai/frontend/static/billing_order.css`
- `chatai/frontend/templates/billing_order.html`
- `chatai/tests/test_157_facturacion_trabajador_comision.py`

## Tests
```
pytest chatai/tests/test_157_facturacion_trabajador_comision.py chatai/tests/test_156_facturacion_header_pivot_zero.py chatai/tests/test_146_facturacion_pivot_total_mismatch.py -v
```

## Manual QA
1. Ir a `/odoo/facturacion`, filtrar HERBI ML SPA / KONTROLAG / 26/08/2026–01/09/2026, Generar orden
2. Verificar GLOSA: Total trabajadores $175.000, Adicional $87.500, Total a Pagar $262.500
3. En la tabla, cada celda diaria muestra solo el pago al trabajador (p. ej. $25.000)
4. Debajo de la tabla: Subtotal $175.000, Adicional $87.500, Total $262.500
5. Descargar el PDF y confirmar el mismo desglose
