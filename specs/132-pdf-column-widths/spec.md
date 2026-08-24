# Optimizar anchos de columna en todos los PDFs de tarjas
# Path: specs/132-pdf-column-widths/spec.md
issue: #132 · branch: 132-pdf-column-widths · date: 2026-08-24

## What
Todas las tablas de los PDFs de tarjas (individuales y el PDF unificado de `/reportes`, que desde el issue #116 comparten el mismo código) ahora tienen anchos de columna explícitos, angostados al contenido real en vez de estirarse al 100% del ancho de página. De paso se encontraron y corrigieron **dos bugs reales** de layout (no solo estéticos): "Resumen por persona" y "Jornadas por trabajador" tenían columnas colapsadas con texto solapado por falta de control de ancho.

## Acceptance
- [x] Ninguna tabla se estira innecesariamente cuando su contenido es corto (nombres, montos, fechas cortas)
- [x] Todo el texto sigue siendo completamente legible, sin solapamientos ni cortes
- [x] Los 2 bugs de solapamiento encontrados (resumen-persona, jornadas-trabajador) quedan corregidos
- [x] Las tablas pivot (fechas dinámicas) angostan la tabla completa cuando hay pocas fechas, en vez de repartir el espacio sobrante entre columnas ya angostas

## Context
- **Cómo se detectó:** el usuario pidió angostar columnas en todos los reportes porque salían "con muchos espacios libres de ancho" y quedaban "muy extensos horizontalmente". Antes de tocar nada se generaron y compararon visualmente (PDF → PNG) los 10 reportes con datos reales para confirmar el problema y encontrar casos límite.
- **Hallazgo no esperado:** dos reportes no solo tenían espacio libre — estaban genuinamente rotos. "Resumen por persona" (tabla `<table border="1">` sin ningún control de ancho) mostraba el encabezado "Trabajador" colapsado a una columna casi invisible, con "Tipo de pago" solapando el texto de "Fecha". "Jornadas por trabajador" mostraba la columna "Contratista" colapsada a la letra "C", con el valor completo ("HERBI ML SPA") partido en 3 líneas por palabra. Ninguno de los dos tenía anchos explícitos — dependían por completo del layout automático de reportlab, que ya había fallado así antes (issues #108, #117).
- **Causa raíz general:** `_PDF_CSS` define `table { width: 100%; ... }` como base. Sin `table-layout:fixed` + anchos explícitos por columna, cualquier tabla —sin importar cuántas columnas tenga o cuán corto sea su contenido— se estira a ocupar toda la página, y en los casos con contenido más impredecible (varias columnas de texto corto), reportlab a veces colapsa una columna a casi cero en vez de repartir el espacio proporcionalmente.
- **Tablas pivot (fechas dinámicas):** `_pivot_col_widths()` repartía todo el espacio sobrante entre las columnas de fecha para llenar el 100% de la página, sin importar cuántas fechas hubiera — con pocas fechas (ej. 10-12 en un rango de 2 semanas), cada columna de fecha terminaba mucho más ancha de lo que su contenido (una hora, un monto corto) necesitaba.

## Decisions
- **`_pivot_col_widths()` rediseñada** (usada por 4 reportes: Detalle Contratistas, Horas Extra, Hora Ponderada 9h, y el pivot de "Por operador" tractorista): ahora cada columna de fecha recibe un ancho fijo como % de página (parámetro `date_pct`, default 3.5%; 5% para Hora Ponderada 9h porque sus celdas llevan montos de hasta 7 dígitos y una columna más angosta arriesgaba repetir el bug de solapamiento de los issues #108/#117). Si `fixed_pct + n_dates × date_pct` no supera 100%, la tabla se angosta a ese total real y las columnas se recalculan como % de esa tabla (más angosta), en vez de forzarse a llenar la página. Si se supera el 100% (rango con muchas fechas), se usa el comportamiento anterior tal cual: reparte el espacio sobrante entre las fechas y la tabla queda a ancho completo — sigue evitando el crash "negative availWidth" de reportlab que motivó el issue #52 original.
  - La función ahora también devuelve `widths["table"]`, que el llamador debe aplicar al tag `<table>` mismo (las demás claves son % de esa tabla, no de la página).
- **Tablas planas (sin fechas dinámicas):** cada una recibe un mapa de anchos a mano (mismo patrón que ya usaba Bonos Mensuales desde el issue #117), calculado por columna según el contenido real esperado — texto libre (Labor, Nombre CC, Trabajador, Contratista) se queda con más espacio; valores cortos (CC, Jornadas, Tipo de pago, Costo/hora) se angostan. El ancho total de la tabla se redujo cuando el contenido no lo necesitaba (ej. Jornadas por Trabajador a 55% de página; General Operacional a 80%) y se mantuvo más ancho cuando hay columnas de texto libre largo (Detalle Operacional se queda cerca del 100% porque Labor y Nombre CC pueden ser descripciones largas).
- Se dejaron sin tocar las clases CSS `.summary-wrap`/`.summary-cell`/`.chart-cell` (código muerto desde que el issue #122 quitó el gráfico de torta del PDF de Detalle) — limpiarlas es un cambio distinto, fuera del alcance de este issue.
- El reporte "Por operador" tractorista (`/api/tarjas/tractorista/download-pdf`) no es parte de los 10 reportes unificados del issue #116 (no está en `AVAILABLE_REPORTS`), pero también usa `_pivot_col_widths` para su tabla pivot — se benefició del mismo fix sin cambios adicionales.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_pivot_col_widths()` — rediseñada (ver Decisions); nuevo parámetro `date_pct`
  - 4 usos de `_pivot_col_widths` actualizados para aplicar `widths["table"]` al `<table>` y con anchos fijos más angostos (`_build_contratista_html`, `_build_resumen_horas_html`, `_build_hora_ponderada_html`, el pivot de "Por operador" tractorista)
  - `_build_resumen_persona_html()` — **fix de bug**: agrega `table-layout:fixed` + anchos explícitos (antes sin ningún control de ancho)
  - `_build_jornadas_trabajador_html()` — **fix de bug**: mismo tratamiento
  - `_build_detalle_html()` / `_summary_table_html()` — anchos explícitos en ambas tablas (Resumen y Detalle)
  - `_build_general_html()` — anchos explícitos en ambas tablas (Ganancia promedio por labor y Ranking por persona)
  - `_build_detalle_tractorista_html()` / `_build_general_tractorista_html()` — anchos explícitos
  - `_build_bono_mensual_html()` — angosta la tabla completa de 100% a 88% de página, manteniendo las proporciones por columna ya afinadas en el issue #117

### Tests
- `chatai/tests/test_52_fix_pdf_pivot_mismatch.py` — el test que verificaba que los anchos siempre sumaran 100% de la página se dividió en 3: suma 100% de la tabla propia (nuevo comportamiento), fallback a ancho completo cuando hay muchas fechas, y angostamiento real cuando hay pocas.
- `chatai/tests/test_122_pdf_detalle_sin_grafico.py` — un assert de markup exacto (`<th class="num">%</th>`) se relajó para no depender del atributo `style` agregado.

## Routes
Sin cambios de rutas — mismos endpoints, mismos datos, solo cambia el CSS/HTML de layout.

## Tests
```
pytest tests/test_52_fix_pdf_pivot_mismatch.py tests/test_122_pdf_detalle_sin_grafico.py -v
20 passed

pytest tests/ -q
303 passed, 2 failed (test_50_odoo_export_tractorista.py — preexistente, no relacionado)
```
Verificación visual manual (PDF → PNG) de los 10 reportes con datos reales: sin solapamientos, columnas angostadas, texto completamente legible.

## Manual QA
1. Descargar el PDF de "Resumen por persona" y "Jornadas por trabajador" (los dos reportes rotos) — confirmar que el texto ya no se solapa y las columnas son legibles.
2. Descargar "Detalle Operacional" y "General Operacional" — confirmar que las columnas de montos/porcentajes ya no tienen espacio libre excesivo, y que Labor/Nombre CC siguen mostrando el texto completo (con wrap si es necesario).
3. Descargar "Hora Ponderada 9h" con un rango corto (1-2 semanas) — confirmar que no hay solapamiento en las celdas de dinero (el caso que motivó los issues #108/#117).
4. Repetir 1-3 desde el PDF unificado de `/reportes` — deben verse idénticos a los individuales (garantía del issue #116).
