# La orden de compra no puede responder 500
# Path: specs/174-oc-no-500/spec.md
date: 2026-09-30

## What

En producción, Generar orden en `/odoo/tarjas` respondió HTTP 500
(`Error al generar`) para AGROSERVICIOS C Y G SPA / ZUÑIGA /
23–29 sep 2026, justo después de publicar el filtro que saca
tractoristas de los reportes de cuadrilla.

La consulta SQL sí terminaba. Esa semana no tiene labores de cuadrilla
(solo Tractorista), así que devolvía cero filas. Después del fetch, el
código hacía `from tarjas_controller import _nombre_cc_label`. Cloud Run
arranca la app como `chatai.backend.main` y ese módulo no existe con
ese nombre: el paquete es `controllers.tarjas_controller`. El import
lanzaba `ModuleNotFoundError` y la pantalla de pago caía, también
cuando el resultado correcto era una orden vacía.

El Excel de Odoo de cuadrilla no cambió de líneas ni de montos. La
orden de compra tractorista no se tocó.

## Acceptance criteria

- [x] `_purchase_order_lines` importa `_nombre_cc_label` desde `controllers.tarjas_controller`.
- [x] AGROSERVICIOS / ZUÑIGA / 2026-09-23..29 responde `rows: []` y `header: null`, no 500.
- [x] MULTISERVICIOS BONHOMIA SPA / ZUÑIGA / 2026-09-02..08 sigue generando la orden (total $7.938.850).
- [x] Ninguna línea de esa orden es tipo de pago Tractorista.

## Context

- El filtro `not_tractorista_sql()` sigue en la orden de compra, la facturación y las notas. No es la causa del 500.
- La vista `tarjas_reporte_odoo` ya excluía tractoristas desde el 15 de abril. Esas filas no entran al Excel de cuadrilla.
- Reportado en intranet: `/odoo/tarjas?fil-from=2026-09-23&fil-to=2026-09-29&fil-empresa=ZUÑIGA&fil-contratista=AGROSERVICIOS C Y G SPA`.
