# Spec #163 — Export Odoo usa Costo Empresa; UI muestra total CLP

## What

El export Odoo (`tarjas_reporte_odoo`) usaba `pagar_efectivo` (total_trabajado +
total_contratista) como `order_line/price_unit`, produciendo montos ~$65.290 más
altos que el header de la Orden de Compra. El fix aplica los factores Costo Empresa
(×1.45 al día, ×1.50 trato) directamente sobre `total_trabajado` — la misma base
que usa el header de la OC.

## Acceptance criteria

- Agregar columna `total_unitario_empresa` a `tarjas_reporte` con fórmula:
  `ROUND(AVG(total_trabajado × factor), 2)` donde factor = 1.50 trato, 1.45 al día, 1.0 otros.
- La vista `tarjas_reporte_odoo` usa `total_unitario_empresa` como `order_line/price_unit`.
- El endpoint `GET /api/tarjas/export-preview` devuelve `total_ok_clp`.
- El modal de exportación muestra el total CLP exportable junto al total de jornadas.
- Test de regresión: `SUM(qty × price_unit)` export ≈ total Costo Empresa OC para mismo rango.

## Context

- `sql/tarjas/01_views_reporte.sql` — vista `tarjas_reporte`; agregar `total_unitario_empresa`
- `sql/tarjas/02_views_odoo.sql` — vista `tarjas_reporte_odoo`; cambiar `order_line/price_unit`
- `chatai/backend/controllers/purchase_orders_controller.py` — endpoint export-preview (~línea 590); agregar `total_ok_clp` en respuesta
- `chatai/frontend/static/purchase_orders.js` — tfoot del modal; mostrar total CLP
- `chatai/backend/tarjas_empresa.py` — factores de referencia: FACTOR_EMPRESA_AL_DIA=1.45, FACTOR_EMPRESA_TRATO=1.50

## Decisions

- Se agrega `total_unitario_empresa` directamente en `tarjas_reporte` (no solo en `tarjas_reporte_odoo`) para que la columna quede disponible para futuras superficies sin duplicar la lógica del CASE.
- El CASE en SQL replica exactamente los factores de `tarjas_empresa.py` (1.50 trato, 1.45 al día, 1.0 resto) para no importar código Python en la vista.
- `total_ok_clp` es un alias de `total_ok` en la respuesta del endpoint — misma variable, clave adicional para que el front pueda evolucionar sin romper código que ya use `total_ok`.
- El test #130 `test_130_visor_and_excel_totals_match_within_rounding` fue reemplazado por `test_130_odoo_export_row_count_not_inflated` porque el cambio de precio_unit hace que los totales monetarios de `tarjas_reporte` y `tarjas_reporte_odoo` sean intencionalmente distintos. El invariante correcto para #130 es el conteo de filas, no el monto.

## Implemented

- `sql/tarjas/01_views_reporte.sql` — agrega columna `total_unitario_empresa` con CASE de factores
- `sql/tarjas/02_views_odoo.sql` — `Lineas del pedido/Precio un.` y `order_line/price_unit` cambian de `r.total_unitario` a `r.total_unitario_empresa`
- `chatai/backend/controllers/purchase_orders_controller.py` — respuesta de `/api/tarjas/export-preview` incluye `total_ok_clp`
- `chatai/frontend/static/purchase_orders.js` — tfoot del modal muestra `$totalClpFmt` junto a las jornadas exportables
- `chatai/tests/test_163_export_odoo_costo_empresa.py` — 4 tests de regresión nuevos
- `chatai/tests/test_130_tarjas_odoo_view_no_fanout.py` — test de totales monetarios reemplazado por test de conteo de filas

## Tests

1 passed (estático, sin DB) · 3 pendientes de correr contra la DB de producción · isolation: N/A (sin data cross-tenant)

## Manual QA

1. Abrir la pantalla Orden de Compra para MULTISERVICIOS BONHOMIA SPA / ZUÑIGA, semana 2026-08-12 a 2026-08-18. Anotar el total del header.
2. Hacer clic en "Exportar archivo Odoo" → verificar que el modal muestra el total CLP exportable (debería estar cercano al total del header de la OC, no $65.290 más alto).
3. Descargar el xlsx → abrir en Excel → sumar `order_line/product_qty * order_line/price_unit` → confirmar que cuadra con el header de la OC.
