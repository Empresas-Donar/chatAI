# Spec: Reporte Odoo para Tractoristas (#50)

## What

Implementar exportación Excel en formato de importación Odoo para registros de tipo Tractorista. Actualmente `appsheet.tarjas_reporte_odoo` excluye tractoristas explícitamente (`WHERE tipo_pago NOT IN ('Tractorista')`). Los tractoristas usan `horas_extras` como qty (no jornadas) y `total_tractor / horas_extras` como precio unitario.

## Acceptance criteria

- [ ] Vista `appsheet.tarjas_reporte_odoo_tractorista` existe en PostgreSQL y devuelve filas correctas para tractoristas (`horas_extras > 0`)
- [ ] Endpoint `GET /api/tarjas/tractorista/odoo-export` retorna Excel con formato de importación Odoo
- [ ] `order_line/product_qty` = suma de `horas_extras` (no conteo de filas)
- [ ] `order_line/price_unit` = `total_tractor / horas_extras` (tarifa por hora), ponderado si hay múltiples labores
- [ ] Filas sin `product_id` o con CC no mapeado son excluidas y reportadas en header `X-Excluded-Amount`
- [ ] Los 4 niveles de fallback para `product_id` funcionan igual que en reporte de cuadrilla
- [ ] Botón "Exportar Odoo" en `tarjas_detalle_tractorista.html`
- [ ] Test de regresión que verifica que qty usa `horas_extras` y no `jornadas`

## Context

La vista base `tarjas_reporte` agrega por `(contratista, nombre_campo, fecha, tipo_pago, cuartel_cc, labor)` usando window functions, pero no incluye `horas_extras` como campo agregado. Por decisión del issue (comentario bedomax 2026-07-29), la vista de tractoristas se construye **directamente desde `tarjas_pagos`** (igual que hace `tarjas_reporte` internamente), sin depender de `tarjas_reporte`.

Archivos clave:
- `sql/tarjas/02_views_odoo.sql` — modelo a seguir (cuadrilla)
- `sql/tarjas/01_views_reporte.sql` — patrón de window functions
- `chatai/backend/controllers/tarjas_controller.py` líneas ~3258-3397 — endpoint `odoo-export` existente
- `chatai/frontend/templates/tarjas_detalle_tractorista.html` — template donde agregar botón
- `chatai/frontend/static/tarjas_detalle_tractorista.js` — lógica de botones

La columna `horas_extras` es NUMERIC (migrada en issue #38, `07_fix_numeric_types.sql`). La columna de maquina puede ser `maquina` o `máquina` según el predio (no relevante para la vista SQL pero sí para el endpoint).

El campo `total_tractor` en `tarjas_pagos` es el costo total de maquinaria a pagar al tractorista.

## Decisions

- Vista construida directo desde `appsheet.tarjas_pagos` (no usa `tarjas_reporte`) para poder agregar `SUM(horas_extras)` en la partición correcta sin modificar la vista base.
- La partición es `(contratista, nombre_campo, fecha::DATE, cuartel_cc, labor)` — igual que cuadrilla pero sin `tipo_pago` (todos son tractorista).
- `order_line/price_unit` = `SUM(total_tractor) / NULLIF(SUM(horas_extras), 0)` — ponderado automáticamente por la agregación SQL.
- El botón "Exportar Odoo" se agrega a `tarjas_detalle_tractorista.html` en la barra de acciones (junto a Excel y PDF), activado con los mismos filtros activos.
- No requiere parámetro `nc_total` (las notas de crédito no aplican a tractoristas).
- Se requiere `contratista` y `campo` no vacíos para exportar (igual que cuadrilla).

## Implemented

- `sql/tarjas/08_views_odoo_tractorista.sql` — nueva vista SQL `appsheet.tarjas_reporte_odoo_tractorista`
- `chatai/backend/controllers/tarjas_controller.py` — nuevo endpoint `GET /api/tarjas/tractorista/odoo-export`
- `chatai/frontend/templates/tarjas_detalle_tractorista.html` — botón "Exportar Odoo" en barra de filtros
- `chatai/frontend/static/tarjas_detalle_tractorista.js` — lógica de clic del botón Odoo
- `chatai/tests/test_50_odoo_export_tractorista.py` — tests de regresión

## Tests

16 passed, 0 failed · isolation: N/A (static analysis tests, no cross-farm DB queries)

## Manual QA

1. En `/tarjas/detalle-tractorista`, seleccionar un contratista y campo específicos con fechas que tengan datos de tractorista. Hacer clic en "Exportar Odoo". El archivo Excel debe descargarse con columnas: `partner_id`, `order_line/product_id`, `order_line/product_qty`, `order_line/analytic_distribution`, `order_line/price_unit`.
2. Verificar que `order_line/product_qty` sea la suma de `horas_extras` (no el conteo de filas). Comparar contra la suma manual desde la vista de detalle tractorista.
3. Verificar que filas sin `product_id` o CC no mapeado aparecen excluidas con un `alert` mostrando el monto excluido.
