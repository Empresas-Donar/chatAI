# Spec #162 — Recargos Costo Empresa invertidos

## What

Los factores de Costo Empresa estaban invertidos en toda la plataforma:
Al Día usaba ×1.45 y Trato ×1.50. La regla de negocio es la inversa:
**45 % a trato y 50 % al día**. Eso dañaba OC, Detalle, Facturación,
Notas, Export Odoo y PDFs.

## Acceptance criteria

- [x] `tarjas_empresa.py`: Al Día × 1.50, Trato × 1.45. NUNCA invertir.
- [x] `tarjas_detail.js` **no duplica** factores; solo renderiza `total_empresa` / `recargo` del API.
- [x] Docs Claude/Cursor congelan: Trato +45 %, Al Día +50 %.
- [x] Tests actualizados con montos recalculados (BONHOMIA / ZUÑIGA).
- [x] No quedan mapeos invertidos de Costo Empresa en el repo.
- [x] Export Odoo xlsx (OC y Notas) y preview se precifican con `total_empresa()` (mismo grano que la OC).

## Context

Fuente de verdad: `chatai/backend/tarjas_empresa.py`.
JS de Detalle solo pinta campos del API (sin factores).
Docs: `.cursorrules`, `CLAUDE.md`, `AGENTS.md`, `.cursor/rules/tarjas-costo-empresa.mdc`.

Costo Empresa: Trato × 1.45 (+45 %). Al Día × 1.50 (+50 %). NUNCA invertir. Única fuente: `tarjas_empresa.py`.

## Decisions

- La verdad de negocio ES trato 45 % / al día 50 %. Se elimina la idea de
  que "AppSheet está invertido vs plataforma".
- Sigue sin usarse `total_pagar` (a menudo 0) ni `total_trabajado +
  total_contratista` como monto facturado. El costo facturado es
  `total_trabajado × factor` via `total_empresa()`.
- Vistas SQL (`tarjas_reporte`, `tarjas_reporte_odoo`) siguen en
  `pagar_efectivo` para mapeo Odoo (product_id / analytic). El precio
  facturado del xlsx sale de `costo_empresa_odoo_lines()` → `total_empresa()`.

## Implemented

- `chatai/backend/tarjas_empresa.py`
- `chatai/frontend/static/tarjas_detail.js`
- `chatai/backend/controllers/chat_controller.py`
- `chatai/backend/controllers/purchase_orders_controller.py` (`costo_empresa_odoo_lines`)
- `chatai/tests/test_costo_empresa_invariant.py`
- `.cursorrules`
- `CLAUDE.md`
- `AGENTS.md`
- `.cursor/rules/tarjas-costo-empresa.mdc`
- `specs/160-resumen-total-empresa/spec.md`
- `chatai/tests/test_detalle_resumen_total_empresa.py`
- `chatai/tests/test_96_pdf_detalle_resumen_grafico.py`
- `chatai/tests/test_oc_cuadra_detalle_costo_empresa.py`
- `chatai/tests/test_156_facturacion_header_pivot_zero.py`
- `chatai/tests/test_157_facturacion_trabajador_comision.py`
- `chatai/tests/test_costo_empresa_invariant.py`

## Tests

44 passed on the Costo Empresa suite. 1 preexisting fail (`test_96_badge_class_fallback_empty`, badge-bono desde #159). 1 flaky DB timeout retried and passed. Isolation: ✅ (`test_160_campo_isolation`, `test_156_*_isolation`, `test_157_*_isolation`).

## Manual QA

1. Abrir `/tarjas/detalle?fil-from=2026-09-02&fil-to=2026-09-08&fil-contratista=MULTISERVICIOS+BONHOMIA+SPA&fil-empresa=ZUÑIGA`
2. Resumen: Recargo Al Día **+50 %**, Trato **+45 %**. Al Día Costo Empresa **$5.012.750**, Trato **$2.926.100**, footer **$7.938.850**.
3. Comparar los mismos filtros en `/odoo/tarjas` y `/odoo/facturacion`: Total a Trato y Total Al Día deben cuadrar con el Resumen.
