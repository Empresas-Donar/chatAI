# Total distinto en pantalla vs PDF en Orden de Compra / Orden de Facturación
# Path: specs/88-screen-pdf-total-mismatch/spec.md
issue: #88 · branch: 88-screen-pdf-total-mismatch · date: 2026-08-06

## What
El total "a pagar" mostrado en pantalla en la Orden de Compra / Orden de Facturación por contratista no coincide con el total del PDF descargado para el mismo contratista y mismo rango de fechas.

## Acceptance
- [x] El total mostrado en pantalla (`/api/purchase-orders`) coincide exactamente con el total del PDF (`/api/purchase-orders/print-pdf` y `/api/odoo/facturacion/pdf`) para el mismo contratista, empresa y rango de fechas.
- [x] El total "a pagar" en pantalla y en PDF es igual a `SUM(total_labor)` de todas las filas de `appsheet.tarjas_reporte` para ese contratista/empresa/rango, sin descartar filas cuyo `tipo_pago` no sea exactamente "trato" o "Al dia".
- [x] Regresión cubierta con test automatizado usando el caso real reportado (MULTISERVICIOS BONHOMIA SPA / ZUÑIGA / 2026-07-29 a 2026-08-04).

## Context
- Módulo: `chatai/backend/controllers/purchase_orders_controller.py`
- Endpoint pantalla: `GET /api/purchase-orders` → función `get_purchase_order` (usado por `purchase_orders.js` para "Orden de Compra" y por `billing_order.js` para "Orden de Facturación").
- Endpoint PDF "Orden de Compra": `GET /api/purchase-orders/print-pdf` → función `purchase_order_print_pdf`.
- Endpoint PDF "Orden de Facturación": `GET /api/odoo/facturacion/pdf` → función `billing_order_pdf`.
- Constantes: `_PAYMENT_TYPE_TRATO = "trato"`, `_PAYMENT_TYPE_AL_DIA = "Al dia"`.
- Todas las consultas parten de la misma vista `appsheet.tarjas_reporte` filtrando por `contratista`, `nombre_campo` y `fecha BETWEEN`.

## Decisions
- `get_purchase_order` (pantalla) calculaba `total_al_dia` filtrando `tipo_pago == _PAYMENT_TYPE_AL_DIA` (coincidencia exacta con el string `"Al dia"`). Cualquier fila cuyo `tipo_pago` no fuera exactamente `"trato"` ni exactamente `"Al dia"` (p.ej. `"Bono"`) quedaba fuera de `total_trato` y de `total_al_dia`, y por lo tanto fuera del total general mostrado en pantalla.
- Ambos endpoints de PDF (`purchase_order_print_pdf`, `billing_order_pdf`) ya calculaban `total_al_dia` como "todo lo que no es trato" (`tipo_pago != _PAYMENT_TYPE_TRATO` / `!= "trato"`), es decir catch-all — por eso su total sí incluye filas `"Bono"` u otras variantes, agrupadas dentro de "Al Día".
- Fix elegido: alinear `get_purchase_order` con el patrón catch-all que ya usan ambos endpoints de PDF (`tipo_pago != _PAYMENT_TYPE_TRATO`), en vez de cambiar los PDFs. Es el cambio mínimo, ya está probado en dos lugares del mismo archivo, y garantiza que el total de pantalla sea siempre `SUM(total_labor)` completo — igual que el PDF — sin descartar filas silenciosamente por diferencias de texto en `tipo_pago`.
- No se modifica la fila por fila (`data`) que devuelve el endpoint, solo el cálculo de `total_al_dia`/`total`/`pct_al_dia` en el `header`. Cada fila individual con su `tipo_pago` real sigue viéndose en la tabla de detalle de la pantalla; el fix solo corrige el total agregado.
- El trigger `trg_fix_total_jornada` (#62/#82) y el cálculo de `total_jornada` por trabajador se descartaron explícitamente como causa: ese bug es sobre el cálculo individual de `total_jornada` en `appsheet.tarjas_pagos`, no sobre cómo se agregan los totales por `tipo_pago` en el reporte de Orden de Compra/Facturación. Se verificó que el trigger sigue presente y no interviene en esta vista.

## Implemented
- `chatai/backend/controllers/purchase_orders_controller.py` — `get_purchase_order`: `total_al_dia` ahora se calcula como `tipo_pago != _PAYMENT_TYPE_TRATO` (catch-all), igual que `purchase_order_print_pdf` y `billing_order_pdf`, en vez de la coincidencia exacta `tipo_pago == _PAYMENT_TYPE_AL_DIA`.
- `chatai/tests/test_88_screen_pdf_total_mismatch.py` — test de regresión con el caso real reportado + test de aislamiento cross-farm.

## Routes
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/purchase-orders | Sin cambio de firma — el `header.total` devuelto ahora es correcto (catch-all) |

## Tests
```
pytest tests/test_88_screen_pdf_total_mismatch.py -v
5 passed in 6.61s
```
Regresión verificada en ambos sentidos: con el código anterior (exact-match `== "Al dia"`) las 2 pruebas de total fallan reproduciendo exactamente los montos reportados ($8.014.183 pantalla vs $8.117.826 PDF); con el fix aplicado, las 5 pruebas pasan.
Cross-farm isolation: ✅

Suite completa (`pytest tests/ -v`, excluyendo despacho): 179 passed, 2 failed. Las 2 fallas (`test_50_odoo_export_tractorista.py`) son preexistentes y no relacionadas — verifican contenido de `sql/tarjas` y del controlador de tractoristas (módulo distinto, no tocado por este fix; el diff de este cambio se limita a 7 líneas en `get_purchase_order`).

## Manual QA
1. Ir a `/odoo/tarjas`, seleccionar contratista "MULTISERVICIOS BONHOMIA SPA", empresa "ZUÑIGA", rango 29/07/2026–04/08/2026, click "Generar orden". Anotar el "Total a Pagar" en pantalla.
2. Click "Descargar PDF" (o `print-pdf`) y verificar que el total del PDF sea idéntico al de pantalla ($8.117.826).
3. Repetir en `/odoo/facturacion` (Orden de Facturación) con los mismos filtros y verificar que el total en pantalla y el del PDF (`/api/odoo/facturacion/pdf`) también coincidan.

## Deferred
- Las filas con `tipo_pago = "Bono"` siguen agrupándose visualmente como "Al Día" tanto en pantalla como en PDF (comportamiento preexistente, ya presente en ambos PDFs antes de este fix). Separar "Bono" como categoría propia en la UI queda fuera de alcance de este issue — el bug reportado es la inconsistencia entre pantalla y PDF, no el agrupamiento de categorías.
