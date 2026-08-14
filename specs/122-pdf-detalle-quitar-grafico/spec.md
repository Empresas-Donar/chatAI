# PDF Detalle Operacional: quitar gráfico, agregar % en Resumen, y ajustar columnas de Detalle
# Path: specs/122-pdf-detalle-quitar-grafico/spec.md
issue: #122 · branch: 122-pdf-detalle-quitar-grafico · date: 2026-08-14

## What
El PDF de "Detalle Operacional" (`/api/tarjas/detalle/download-pdf`) ya no muestra el gráfico de torta; la tabla Resumen ahora tiene una columna "%" después de "Jornadas"; la tabla Detalle cambia "Horas"/"Unitario" por "Nombre CC"; y "% pago" en Detalle se calcula contra (Al Día + Trato), no contra el total de su propio tipo de pago.

## Acceptance
- [x] El PDF de Detalle Operacional ya no incluye el gráfico de torta.
- [x] La tabla Resumen tiene una columna "%" después de "Jornadas" con el porcentaje de cada tipo de pago sobre el total.
- [x] La tabla Detalle ya no muestra "Horas" ni "Unitario".
- [x] La tabla Detalle muestra el nombre del centro de costo (join contra `appsheet.tarjas_cc.cultivo`).
- [x] "% pago" en Detalle = total de la fila / (total Al Día + total Trato) — aplicado en pantalla, Excel y PDF porque comparten la misma consulta.

## Context
- Módulo: `chatai/backend/controllers/tarjas_controller.py`
- `_query_detalle_rows` (compartida por `/api/tarjas/detalle` JSON, el Excel y el PDF) calculaba `pct_pago` con `SUM(SUM(total_labor)) OVER (PARTITION BY tipo_pago)` — el % de una fila "trato" era relativo al total de "trato" solamente, no al total general.
- `appsheet.tarjas_reporte` puede traer más de 2 valores de `tipo_pago` en el mismo rango de fechas: además de `trato`/`Al dia` existen filas `Bono` y `Tractorista` (verificado contra la DB real, rango 2026-07-01/2026-07-31, campo ISLA DE MAIPO). El pedido explícito del usuario fue dividir por "al día + trato" — no por el total general de `tarjas_reporte` — así que el denominador excluye Bono/Tractorista aunque existan filas de esos tipos en el resultado.
- `appsheet.tarjas_cc` (columnas: `id_cc`, `cultivo`, `id_campo`, `valor_odoo`) ya se usa en otras vistas (`sql/tarjas/02_views_odoo.sql`, `08_views_odoo_tractorista.sql`) con el patrón `LEFT JOIN appsheet.tarjas_cc cc ON cc.id_cc::text = r."CC"::text` — se reutiliza el mismo patrón acá. El nombre del CC es la columna `cultivo`; algunos CC tienen `cultivo` igual a su propio código (dato real verificado en la DB, no un bug del join).
- `_pie_chart_b64`, `_ascii_fold` y `_tipo_pago_color` quedaban sin ningún otro llamador tras quitar el gráfico — se eliminaron junto con los imports `math`/`unicodedata` que solo ellas usaban.
- `_build_detalle_html` es compartida con el PDF masivo de `/reportes` (issue #116) — los cambios de columnas/gráfico se aplican ahí también automáticamente porque llama a la misma función.

## Decisions
- El denominador de "% pago" en Detalle se implementó con `SUM(SUM(total_labor)) FILTER (WHERE tipo_pago IN ('trato','Al dia','Al día')) OVER ()` — un `FILTER` sobre la función de ventana, soportado por Postgres, en vez de una subconsulta aparte. Verificado contra datos reales: las filas `trato` + `Al dia` de un rango de fechas suman exactamente 100.0%; las filas `Bono`/`Tractorista` (si existen en el rango) obtienen un `pct_pago` calculado contra ese mismo denominador (pueden superar visualmente el 100% combinado si se muestran junto con Al Día/Trato, pero es el cálculo pedido explícitamente).
- La columna "%" de la tabla Resumen es distinta: sigue siendo el porcentaje de cada fila sobre el total *de esa misma tabla Resumen* (que ya sumaba todos los tipos de pago presentes, sin cambios) — no se tocó esa semántica porque no fue parte del pedido y ya sumaba 100% consistentemente antes de este cambio.
- Se confirmó con el usuario (pregunta explícita) que el fix de la fórmula "% pago" debía aplicarse en pantalla, Excel y PDF, no solo en el PDF, ya que los tres comparten `_query_detalle_rows`.
- Se eliminó código muerto (`_pie_chart_b64`, `_ascii_fold`, `_tipo_pago_color`, imports `math`/`unicodedata`) en vez de dejarlo sin usar, siguiendo la convención del proyecto de no dejar código sin llamador.
- El layout de la tabla Resumen pasa de dos columnas (tabla + gráfico) a una tabla de ancho completo (`.summary-wrap`/`.summary-cell`/`.chart-cell` se eliminan del CSS por quedar sin uso).

## Implemented
### Controllers
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_query_detalle_rows`: agrega `cc.cultivo AS centro_costo_nombre` vía `LEFT JOIN appsheet.tarjas_cc`, corrige la fórmula de `pct_pago`.
  - `_summary_table_html`: agrega columna "%" (encabezado, filas y fila Total).
  - `_build_detalle_html`: quita el bloque del gráfico; la tabla Detalle quita `Horas`/`Unitario`, agrega `Nombre CC`.
  - Eliminados: `_pie_chart_b64`, `_ascii_fold`, `_tipo_pago_color`, imports `math`/`unicodedata`.
  - `_PDF_CSS`: quita `.summary-wrap`, `.summary-wrap td`, `.summary-cell`, `.chart-cell`, `.chart-cell img`; `.summary-table` pasa a ancho completo.

### Tests
- `chatai/tests/test_96_pdf_detalle_resumen_grafico.py`: se quitan los tests de `_pie_chart_b64`/`_ascii_fold`/`_tipo_pago_color` (funciones eliminadas) y la aserción de imagen embebida del test de regresión original; el resto de la cobertura de #96 (Resumen presente en el PDF) se mantiene.
- `chatai/tests/test_122_pdf_detalle_sin_grafico.py` (nuevo): columna "%" en Resumen, `centro_costo_nombre` en las filas, fórmula de `pct_pago` (suma 100% entre Al Día+Trato, coincide con cálculo manual), PDF sin imágenes embebidas, columnas Detalle (`Nombre CC` presente, `Horas`/`Unitario` ausentes), aislamiento por campo del denominador de `pct_pago`.

## Routes
Sin cambios de rutas — mismo endpoint `GET /api/tarjas/detalle/download-pdf` y `GET /api/tarjas/detalle` (JSON), ahora con `pct_pago` recalculado.

## Tests
```
pytest tests/test_96_pdf_detalle_resumen_grafico.py tests/test_122_pdf_detalle_sin_grafico.py -v
18 passed

pytest tests/ -q -k "not test_50_odoo_export_tractorista"
263 passed, 16 deselected
```
(`test_50_odoo_export_tractorista` falla igual en HEAD sin este branch — preexistente, no relacionado, BigQuery/Odoo.)

Cross-farm isolation: ✅ (`test_122_pct_pago_scoped_to_filtered_campo` — filtrando por un campo, las filas Al Día+Trato de ese campo suman 100% por sí solas, confirmando que la función de ventana no arrastra totales de otro campo).

## Manual QA
1. Ir a "Detalle de la semana", aplicar un rango con datos, clic en "PDF" → el PDF no debe mostrar gráfico; la tabla Resumen debe mostrar una columna "%" con los porcentajes de cada tipo de pago.
2. En la tabla Detalle del mismo PDF → no debe haber columnas "Horas" ni "Unitario"; debe haber una columna "Nombre CC" con el nombre del centro de costo.
3. Sumar manualmente el "% pago" de todas las filas "Trato" + "Al Día" de la tabla Detalle → debe dar ~100%.
4. Verificar en pantalla (`/tarjas/detalle`) y en el Excel descargado que la columna "% del pago"/`pct_pago` cambió de valor respecto a antes (ya no es relativo solo a su propio tipo de pago).

## Deferred
- No se investiga por qué algunos `tarjas_cc.cultivo` son iguales a su propio `id_cc` (ej. CC 400, 861) — es un dato preexistente en la tabla, fuera de alcance de este issue.
- No se toca la columna "%" de la tabla Resumen para excluir Bono/Tractorista de su denominador — a diferencia de "% pago" en Detalle, no fue parte del pedido explícito.
