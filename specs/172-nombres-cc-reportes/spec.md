# Nombres de CC en reportes de tarjas (catálogo Excel + overlay sync)
# Path: specs/172-nombres-cc-reportes/spec.md
issue: #172 · branch: 172-nombres-cc-reportes · date: 2026-09-28

## What
Los reportes de tarjas muestran códigos de centro de costo (800, 878) como si fueran nombres de huerto. El catálogo Excel de «Códigos de Distribución Analítica» tiene el nombre humano (800 = CAMPO ZÚÑIGA). Esta implementación siembra ese catálogo, lo aplica a `tarjas_cc.cultivo` cuando el cultivo está vacío o es igual al código, y muestra **Nombre CC** en las superficies de reporte.

El issue #171 queda como follow-up para traer el nombre desde Odoo/BigQuery. AppSheet (dropdown de registro) queda fuera de alcance.

## Acceptance criteria
<!-- Copiado del issue #172 -->
- [x] Existe `appsheet.tarjas_cc_nombres` con seed CSV en el repo (no importar Excel de Downloads en runtime).
- [x] `sync_cc.py` upserta el catálogo y aplica overlay a `tarjas_cc.cultivo` sin pisar nombres Odoo ya distintos del código.
- [x] Detalle (web, PDF, Excel) muestra 800 como **CAMPO ZÚÑIGA**, no `800 (17 cuarteles)`.
- [x] Toda superficie de tarjas que muestre Centro costo / CC incluye Nombre CC desde `tarjas_cc.cultivo`.
- [x] No se duplican factores 1.45/1.50 en JavaScript; no se usa `total_pagar` para Costo Empresa.
- [x] Tests de catálogo/sync y de etiqueta Detalle pasan.
- [x] AppSheet no se toca (queda como nota / trabajo aparte).

## Context
- `appsheet.tarjas_cc.cultivo` es la única fuente de nombre para reportes. JOIN `cc.id_cc = pagos.cuartel_cc`.
- Modelos de distribución (800, 878, …) no tienen nombre en BigQuery `Modelos_Distribucion_Analitica`. El sync caía al fallback numérico.
- Seed: `sql/tarjas/cc_nombres.csv` (126 filas: 25 modelo + 101 cuartel) extraído de los Excel de Odoo. Runtime nunca lee Downloads.
- Overlay: `UPDATE tarjas_cc SET cultivo = n.nombre` solo si cultivo IS NULL, vacío, o igual a `id_cc`. Nombres hoja de Odoo (CEREZOS SANTINA 2014) no se pisan.
- Detalle ya tenía columna Nombre CC + fallback `{código} (N cuarteles)` cuando cultivo seguía siendo el código. Tras el overlay, 800 muestra CAMPO ZÚÑIGA.
- Superficies con CC visible en tabla: Detalle, Hora ponderada, Notas, OC, Tractorista OC, Bono mensual, Calendario, Registros de campo. General / Contratista / Facturación / pivotes tractorista usan CC solo como filtro (el dropdown ahora muestra `800 — CAMPO ZÚÑIGA`).
- Costo Empresa (`tarjas_empresa.py`) está fuera de alcance.

## Decisions
- Una sola fórmula de etiqueta: `_nombre_cc_label` en `tarjas_controller.py`. Si `cultivo` ya es un nombre (≠ código), se muestra ese nombre. El fallback `{código} (N cuarteles)` solo aplica cuando cultivo sigue siendo el código.
- El catálogo Excel vive en el repo (`sql/tarjas/cc_nombres.csv`). `sync_cc.run()` siembra `tarjas_cc_nombres`, overlaya modelos en memoria y hace UPDATE condicional a `tarjas_cc.cultivo`. No se importan Excel de Downloads en runtime.
- No se pisa `cultivo` cuando ya difiere de `id_cc` (nombres hoja de Odoo).
- Reportes reutilizan `tarjas_cc.cultivo` vía LEFT JOIN; no hay una segunda tabla de nombres en las queries de reporte.
- Filtros `fil-cc` pasan a `{id, label}` (`800 — CAMPO ZÚÑIGA`); el value del `<option>` sigue siendo el código para no romper el SQL.
- General, Contratista, Facturación y pivotes tractorista no tienen columna CC en la tabla: solo el filtro. Facturación es pivote trabajador × fecha.
- AppSheet (dropdown de registro) no se toca; hace falta un catálogo aparte. Issue #171 sigue para nombres live desde Odoo/BigQuery.

## Implemented
- `sql/tarjas/27_cc_nombres.sql` — CREATE TABLE `appsheet.tarjas_cc_nombres`.
- `sql/tarjas/cc_nombres.csv` — seed 126 filas (25 modelo + 101 cuartel).
- `apps/sync_cc.py` — `load_cc_nombres_csv`, `seed_cc_nombres`, `overlay_model_cultivo`, `apply_cc_nombres`; `run()` siembra + overlay + apply.
- `chatai/backend/controllers/tarjas_controller.py` — helpers `_nombre_cc_label` / `_cc_filter_label` / `_apply_nombre_cc` / `_fetch_cc_filter_options` / `_attach_cc_nombres`; JOIN cultivo en Detalle, Hora ponderada, Notas, Bono mensual, Tractorista OC preview, Registros de campo, Calendario planes; filtros CC con `{id, label}`.
- `chatai/backend/controllers/purchase_orders_controller.py` — OC lines JOIN cultivo; columna Nombre CC en web/PDF.
- Frontend: `url-filters.js` `fillSelectOptions`; tablas Detalle (ya tenía), Hora ponderada, Notas, OC, Bono mensual, Tractorista OC, Calendario, Registros de campo; dropdowns de `fil-cc`.
- Tests: `test_sync_cc.py` TestCcNombresCatalog; `test_detalle_nombre_cc_valor_odoo.py`; docstring `test_122_pdf_detalle_sin_grafico.py`.

## Routes
Sin rutas nuevas. Superficies existentes que ahora muestran Nombre CC:

| Superficie | Dónde |
|---|---|
| Detalle | web / PDF / Excel / bulk `/reportes` |
| Hora ponderada 9h | web / PDF / Excel / bulk |
| Notas de crédito | web / PDF |
| Orden de compra | web / PDF |
| OC tractorista | títulos de sección CC |
| Bono mensual | web / PDF / Excel / bulk |
| Calendario | detalle registro + planes |
| Registros de campo | card / detalle / Excel |
| Filtros `fil-cc` | General, Detalle, Contratista, Hora ponderada, tractorista |

## Tests
```
pytest chatai/tests/test_sync_cc.py chatai/tests/test_detalle_nombre_cc_valor_odoo.py -v
49 passed, 0 failed
```
Live Detalle `_query_detalle_rows` MULTISERVICIOS BONHOMIA SPA / ZUÑIGA / 2026-09-02..2026-09-08: 800 → CAMPO ZÚÑIGA (3 filas). Isolation catálogo: overlay no pisa cultivo ≠ id_cc (`test_overlay_replaces_code_cultivo`).

`test_112_hora_ponderada_bulk_parity` 3 failed: 0 filas para SERVICIOS AGRICOLAS RD SPA / 2026-07-01..15 (mismo COUNT sin JOIN). No es regresión del overlay; Hora ponderada Bonhomia esa semana sí trae CAMPO ZÚÑIGA.

## Manual QA
1. Detalle: MULTISERVICIOS BONHOMIA SPA, campo ZUÑIGA, 02/09/2026–08/09/2026. CC 800 debe decir **CAMPO ZÚÑIGA** (web, PDF, Excel), no `800 (17 cuarteles)`.
2. Filtro Centro costo en Detalle / General: opción `800 — CAMPO ZÚÑIGA`; al filtrar el value sigue siendo `800`.
3. Hora ponderada 9h misma semana: columna Nombre CC = CAMPO ZÚÑIGA.
4. Notas / OC mismo contratista y semana: columna Nombre CC junto al código.
5. Confirmar que un cuartel hoja (p.ej. 883 CEREZOS SANTINA 2014) no cambió de nombre.

## Deferred
- Nombres live desde Odoo/BigQuery → issue #171.
- Actualizar el dropdown de AppSheet (catálogo de registro) — trabajo aparte, no ChatAI.
