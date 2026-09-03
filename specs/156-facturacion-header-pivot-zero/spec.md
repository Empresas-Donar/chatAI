# Encabezado $0 vs tabla dinámica $175.000 en Orden de Facturación
# Path: specs/156-facturacion-header-pivot-zero/spec.md
issue: #156 · branch: 156-facturacion-header-pivot-zero · date: 2026-09-02

## What
En la pantalla "Orden de Facturación" (`GET /odoo/facturacion`), el encabezado (Total a Trato, Total Al Día, Total a Pagar y el gran total) muestra **$0**, mientras que la tabla dinámica trabajador×fecha debajo muestra **$175.000**, para el mismo contratista/empresa/rango de fechas.

Caso reportado: HERBI ML SPA / KONTROLAG / 2026-08-26–2026-09-01.
URL: https://intranet.empresasdonar.cl/odoo/facturacion?inp-date-from=2026-08-26&inp-date-to=2026-09-01&sel-contractor=HERBI+ML+SPA&sel-company=KONTROLAG

## Acceptance
- [x] El "Total a Pagar" del encabezado coincide con la "Suma total" de la tabla dinámica en la misma página, para el mismo contratista/empresa/rango.
- [x] Ambos coinciden con los totales del PDF (`GET /api/odoo/facturacion/pdf`) para los mismos filtros.
- [x] El pivot de pantalla usa el monto facturable (`total_pagar`, con fallback a `total_trabajado + total_contratista` si `total_pagar` es 0) filtrado por `estado = 'Aprobado'` — el mismo criterio que el PDF / `tarjas_reporte`.
- [x] El reporte operativo `GET /api/tarjas/contratista` (página por persona) no se rompe: sigue mostrando todos los estados y `total_trabajado`.

## Context
- Módulo: `chatai/backend/controllers/purchase_orders_controller.py` + `chatai/frontend/static/billing_order.js`
- La pantalla llama **dos APIs distintas** en paralelo (`billing_order.js` `generate()`):
  1. Encabezado → `GET /api/purchase-orders` (`get_purchase_order`) sobre `appsheet.tarjas_reporte` (`estado = 'Aprobado'`, `SUM(total_labor)` = `SUM(total_pagar)`)
  2. Pivot → `GET /api/tarjas/contratista` (`get_tarjas_contractor_data`) sobre `appsheet.tarjas_pagos` crudo, **sin filtro de estado**, y el JS suma `r.total_trabajado`
- El PDF (`billing_order_pdf`) ya se alineó en #146: header y pivot con `total_pagar` + `estado = 'Aprobado'`. El encabezado de pantalla se alineó con el PDF en #88. **El pivot de pantalla nunca se actualizó** a esas reglas.
- Hipótesis verificadas contra Postgres (HERBI ML SPA / KONTROLAG / 2026-08-26–2026-09-01):
  - **A (descartada):** las 7 filas están `estado = 'Aprobado'`
  - **B (confirmada):** `total_trabajado = 175.000`, `total_contratista = 87.500`, `total_pagar = 0`. La vista `tarjas_reporte` tiene 2 filas con `total_labor = 0`, por eso el encabezado muestra $0. El pivot de pantalla suma `total_trabajado` → $175.000
  - **C (descartada):** `nombre_campo = 'KONTROLAG'` coincide; `_empresa_to_campo` es no-op
- Fórmula de dominio (`sql/tarjas/01_views_reporte.sql`): `total_pagar = total_trabajado + total_contratista`. Las mismas labores CANALETAS AGUAS LLUVIA del 11–12/08/2026 tienen `total_pagar = 37.500` (= 25.000 + 12.500). El monto canónico de este caso es **$262.500**, no $175.000 (pago al trabajador) ni $0
- AppSheet dejó de escribir `total_pagar` ~semana del 24/08/2026 (534 filas Aprobado con `total_pagar = 0` y partes > 0). El trigger `trg_fix_total_jornada` solo rellena `total_pagar` cuando `total_jornada` está desfasado > $500; estas filas tienen `total_jornada` correcto, así que el trigger no interviene
- Relacionado, no duplicado: #146 (PDF pivot vs PDF header), #88 (screen header vs PDF header)

## Decisions
- Hipótesis B, no A: no se ocultan las 7 filas aprobadas. El monto canónico es `total_pagar = total_trabajado + total_contratista` = **$262.500**, no los $175.000 que el pivot viejo mostraba (`total_trabajado`) ni $0
- La pantalla deja de llamar dos APIs. Nuevo `GET /api/odoo/facturacion/data` y el PDF (`billing_order_pdf`) comparten `_fetch_billing_order`: `estado = 'Aprobado'` + `COALESCE(NULLIF(total_pagar, 0), total_trabajado + total_contratista)`. Header y pivot no pueden divergir
- No se modifica `GET /api/tarjas/contratista` ni `get_purchase_order` (Orden de Compra sigue en `tarjas_reporte`). El JS de facturación ya no usa esas APIs
- No se ejecuta el backfill contra producción desde este cambio: AppSheet puede reescribir `total_pagar = 0`. El COALESCE en Python arregla el reporte al desplegar. `sql/tarjas/22_fix_total_pagar_zero.sql` extiende el trigger, hace backfill (excepto Tractorista) y recrea `tarjas_reporte` con el mismo fallback; hay que aplicarlo aparte para que Orden de Compra y el resto de reportes sobre la vista también dejen de mostrar $0
- Si el header JSON viene `null` pero el pivot tiene filas, el JS calcula el total desde el pivot (misma columna `total_pagar`)

## Implemented
### Controllers
- `chatai/backend/controllers/purchase_orders_controller.py` — `_BILLABLE_SQL`, `_fetch_billing_order`, `GET /api/odoo/facturacion/data`; `billing_order_pdf` usa el mismo helper

### Frontend
- `chatai/frontend/static/billing_order.js` — una sola llamada a `/api/odoo/facturacion/data`; el pivot suma `total_pagar`

### SQL (aplicar en Postgres, no corre en el deploy de Cloud Run)
- `sql/tarjas/22_fix_total_pagar_zero.sql`

### Tests
- `chatai/tests/test_156_facturacion_header_pivot_zero.py`

## Routes
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/odoo/facturacion/data | Nuevo. Header + pivot de un solo snapshot |
| GET | /api/odoo/facturacion/pdf | Misma query que `/data`; sin cambio de firma |
| GET | /api/tarjas/contratista | Sin cambios |

## Tests
```
pytest chatai/tests/test_156_facturacion_header_pivot_zero.py chatai/tests/test_146_facturacion_pivot_total_mismatch.py chatai/tests/test_88_screen_pdf_total_mismatch.py -v
13 passed, 1 skipped in ~40s
```
Issue #156 only: 5 passed, 0 failed · isolation: ✅ (`test_156_facturacion_header_pivot_zero_isolation`)

Verificado contra producción (HERBI ML SPA / KONTROLAG / 26/08/2026–01/09/2026):
- `SUM(total_pagar)` almacenado: 0
- `SUM(total_trabajado)`: 175.000 (lo que mostraba el pivot viejo)
- `SUM(total_contratista)`: 87.500
- Monto facturable (fórmula): **262.500** — header, pivot y PDF ahora coinciden en ese valor

## Manual QA
1. Ir a `/odoo/facturacion`, filtrar contratista "HERBI ML SPA", empresa "KONTROLAG", rango 26/08/2026–01/09/2026, Generar orden. Verificar que Total a Pagar, Total Al Día y el gran total muestren **$262.500** (no $0 ni $175.000) y que la fila "Suma total" del pivot sea el mismo monto.
2. Descargar el PDF del mismo filtro y verificar que el encabezado y la "Suma total" del pivot coincidan con la pantalla ($262.500).
3. Abrir `/tarjas/contratista` con los mismos filtros y confirmar que esa página sigue mostrando el total por `total_trabajado` ($175.000) y no se rompió.

## Deferred
- Aplicar `sql/tarjas/22_fix_total_pagar_zero.sql` en Postgres para backfill + trigger + vista (Orden de Compra y demás reportes sobre `tarjas_reporte` seguirán en $0 hasta entonces)
- Corregir AppSheet para que vuelva a escribir `total_pagar` (fuera de este repo)
