# Spec #162 — fix: analytic_distribution con valor nulo pasa el filtro del exportador Odoo

## What

La vista SQL `tarjas_reporte_odoo` genera el campo `order_line/analytic_distribution` agregando
entradas de `cc.valor_odoo` con `jsonb_object_agg(k, ROUND(v::numeric, 2))`. Cuando `valor_odoo`
contiene una clave con valor JSON `null`, `jsonb_each_text` retorna SQL NULL para `v`, por lo que
`ROUND(NULL::numeric, 2) = NULL`. El `jsonb_object_agg` agrega la entrada como `{"410": null}`.

El endpoint de exportación filtra filas problemáticas buscando `LIKE '%"": %'` (clave vacía), pero
este filtro no detecta claves con valor nulo (`{"410": null}`). Las filas afectadas aparecen como
"OK" en el preview, se exportan al XLSX, y al importar en Odoo producen una distribución analítica
que no suma 100%, impidiendo que los usuarios cuadren los pedidos.

La vista para tractoristas (`tarjas_reporte_odoo_tractorista`, archivo 08) tiene el mismo defecto.

## Acceptance criteria (desde el issue)

1. La vista `tarjas_reporte_odoo` filtra entradas con valor NULL antes del `jsonb_object_agg`,
   evitando emitir CCs con porcentaje nulo.
2. El endpoint de exportación detecta y excluye filas cuya distribución analítica contiene
   valores nulos (clave presente pero porcentaje NULL).
3. El endpoint de preview clasifica esas filas como excluidas con motivo legible.
4. Todos los tests existentes siguen pasando.
5. Test de regresión: `valor_odoo` con `{"410": null}` produce fila excluida, no OK.

## Context

Archivos involucrados:
- `sql/tarjas/02_views_odoo.sql` — vista `tarjas_reporte_odoo` (línea 38-39): agregar `WHERE v IS NOT NULL` en el subselect
- `sql/tarjas/08_views_odoo_tractorista.sql` — misma corrección en la vista tractorista (línea 29-30)
- `chatai/backend/controllers/purchase_orders_controller.py` — los dos filtros `NOT LIKE '%%"": %%'` en el endpoint de exportación, y la clasificación de filas en el preview, deben también detectar `null` como valor en el JSON
- `chatai/tests/test_162_fix_analytic_null_export.py` — test nuevo

La única fuente legítima de CCs con valor nulo en `valor_odoo` es: un bug previo en `sync_cc.py`
o en la inserción manual que escribió `{"410": null}` en lugar de omitir ese CC. El fix en la
vista es defensivo — purga esas entradas antes de que lleguen al exportador.

## Decisions

- Se filtra en la vista SQL (`WHERE v IS NOT NULL`) en vez de en el controlador Python, porque la
  vista es la fuente de verdad para ambos endpoints (export y preview) y para cualquier query SQL
  directa; un filtro solo en Python dejaría la vista corrupta para otros consumidores.
- También se ajustan los filtros LIKE en el controlador para detectar el patrón `: null` además
  de la clave vacía, así el detection en la BD cubre ambos casos incluso con datos pre-existentes
  que no pasaron por la vista (e.g. queries directas con GROUP BY en `tarjas_reporte_odoo`).
- La vista tractorista recibe la misma corrección por paridad.

## Implemented

- `sql/tarjas/02_views_odoo.sql` — agregar `WHERE v IS NOT NULL` en el subselect de `jsonb_object_agg`
- `sql/tarjas/08_views_odoo_tractorista.sql` — misma corrección
- `chatai/backend/controllers/purchase_orders_controller.py` — ampliar filtros LIKE para detectar `: null` y ajustar clasificación en preview para valores nulos
- `chatai/tests/test_162_fix_analytic_null_export.py` — test de regresión nuevo

## Tests

13 passed, 0 failed · isolation: ✅ (test_cross_farm_isolation_different_products verifica que dos productos con distinto CC se clasifican independientemente)

## Manual QA

1. Abrir el exportador Odoo, seleccionar un contratista/empresa/período donde el producto `4.1`
   aparecía con `"410": ,` — verificar que esa fila ahora aparece en la sección "Excluidas" con
   motivo "CC con distribución nula" (o que el CC nulo fue eliminado y la fila se exporta con el
   porcentaje restante recalculado).
2. Hacer clic en "Exportar" y abrir el XLSX — verificar que ninguna celda `analytic_distribution`
   contiene `null` como valor en el JSON.
3. En la UI de preview verificar que el total mostrado en "Total exportable" no incluye filas con
   distribución analítica inválida.
