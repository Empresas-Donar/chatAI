# PDFs del reporte unificado deben ser idénticos a sus versiones individuales
# Path: specs/116-pdf-bulk-standalone-parity/spec.md
issue: #116 · branch: 116-pdf-header-date-format-title-parity · date: 2026-08-14

## What
Los 10 reportes de `/reportes` (PDF unificado/combinado) que tienen una versión individual ahora son generados por la **misma función** que su PDF individual — garantizando que sean idénticos, no solo hoy sino para siempre (cualquier fix futuro al PDF individual se refleja automáticamente en el unificado). El único reporte sin contraparte individual en PDF ("Resumen tractorista") mantiene su propia implementación, ahora también usando los mismos helpers compartidos (`_pdf_header`, `_pdf_title`, `_PDF_CSS`).

De paso se encontró y arregló un bug real: el encabezado de **todos** los PDFs de `tarjas_controller.py` mostraba las fechas "Desde"/"Hasta" sin formatear (`2026-07-01` en vez de `01/07/2026`), violando la regla del proyecto "Fechas en UI: DD/MM/YYYY — sin excepciones".

## Acceptance
- [x] Los 10 reportes con PDF individual producen HTML byte-idéntico en pantalla unificada y en su descarga individual, para los mismos filtros
- [x] "Resumen tractorista" (sin PDF individual) sigue funcionando, ahora con el mismo formato de título/encabezado que el resto
- [x] Los chips "Desde"/"Hasta" del encabezado usan DD/MM/YYYY en todos los PDFs de `tarjas_controller.py`
- [x] Verificado visualmente (PDF renderizado a imagen) para "Hora Ponderada 9h" y "General Tractorista" — pixel-idénticos entre individual y unificado

## Context
- **Cómo se llegó a esto:** el usuario reportó que "Hora ponderada 9h" en el PDF unificado no coincidía con el individual (issue #112 ya había alineado el comportamiento numérico, pero no el diseño/encabezado). Al investigar el encabezado se encontró una diferencia real de formato de fecha. Luego el usuario señaló que "Detalle Operacional" y "Bonos Mensuales" **tampoco** coincidían — a esa altura quedó claro que el problema era estructural: `reports_controller.py` reimplementaba cada reporte desde cero en vez de compartir código con `tarjas_controller.py`, así que cualquier fix a un PDF individual (como el propio #108) nunca se propagaba al unificado. El usuario pidió una pasada sistemática en vez de seguir parchando reporte por reporte.
- **Hallazgo al auditar los 10 reportes:** algunos no solo diferían en estilo — `general-tractorista` en el unificado consultaba columnas completamente distintas (dos tablas resumidas: "Ganancia promedio por labor" + ranking top 6) mientras el individual mostraba una sola tabla completa (Trabajador/Contratista/Labor/Tipo de pago/Promedio/Total, sin límite). `resumen-persona` individual ni siquiera usaba `_pdf_header`/`_PDF_CSS` (arma su propio header oscuro con tabla inline), mientras el unificado sí. Los 10 reportes tenían algún grado de divergencia.
- **La corrección:** cada endpoint PDF individual en `tarjas_controller.py` (`download_tarjas_*_pdf`) ahora delega la construcción de su cuerpo HTML (header + tabla) a una función `_build_*_html()` nueva, que el endpoint envuelve en su documento completo (`<!DOCTYPE>`, `<style>{_PDF_CSS}</style>`, `_render_pdf(...)`). `reports_controller.py` importa `tarjas_controller.py` directamente (`import controllers.tarjas_controller as tc`) y llama a esas mismas 10 funciones para armar cada sección del PDF combinado — abandonando la convención anterior de "cada controller duplica sus propios helpers de PDF" que existía desde antes de este issue, porque esa convención era precisamente la causa raíz de la divergencia recurrente.
- **Caso especial — Bonos mensuales:** su página individual filtra por mes calendario completo (`mes=YYYY-MM` → `_mes_range()`). El builder compartido (`_build_bono_mensual_html`) recibe `fecha_inicio`/`fecha_termino` directamente; el endpoint individual sigue resolviendo `mes` a un rango antes de llamarlo. El PDF unificado usa el rango de fechas que ya trae la página `/reportes` (sin mes-lock) — mismo código, distinto rango de entrada, tal como se decidió en el issue #109.
- **Caso especial — Resumen tractorista:** no existe endpoint de PDF individual para este reporte (solo pantalla + Excel), así que no hay nada con qué compartir código. Se mantuvo su implementación local en `reports_controller.py`, pero ahora usa `tc._pdf_header`/`tc._pdf_title` (antes usaba una copia local de `_pdf_header`) para que al menos el título/encabezado sea consistente con el resto del documento combinado.
- **El bug de formato de fecha:** `_pdf_header()` (compartida por los 10 reportes de `tarjas_controller.py`) interpolaba `fecha_inicio`/`fecha_termino` directamente en los chips, sin formatear. Se agregó `_fmt_date_slash()` (DD/MM/YYYY) — deliberadamente separada de la `_fmt_date_display()` ya existente en ese archivo, que usa el formato "1 jul 2026" y la siguen usando varias tablas de detalle (fecha por fila); cambiar esa habría sido un scope mucho más amplio no pedido.

## Decisions
- Se optó por **importar** `tarjas_controller.py` desde `reports_controller.py` en vez de seguir duplicando helpers — rompe la convención previa de "cada controller es independiente", pero esa independencia era la causa raíz del bug recurrente que motivó este issue. `reports_controller.py` pasó de ~1160 líneas (con 10 generadores duplicados) a ~330 líneas.
- Los parámetros de filtro extra que algunos reportes individuales aceptan (CC, Labor, Campo, Mes) siguen sin estar expuestos en la página `/reportes` — no cambió el alcance de filtros del PDF unificado, solo se garantizó que, para los filtros que sí comparte (fecha, empresa, contratista), el resultado sea idéntico.
- El título de cada sección del PDF unificado ahora usa el mismo `_pdf_title()` (formato "Tarjas-Reporte {Nombre}-{Contratista}") que su PDF individual — antes el unificado tenía títulos genéricos propios ("General — Tarjas Contratistas", etc.). Esto genera una consecuencia visible: el test de aislamiento del issue #54 (que afirmaba que el PDF unificado *nunca* debía tocar sus títulos) quedó con la premisa invertida a propósito; se actualizó para verificar lo contrario.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_fmt_date_slash()` — nuevo helper DD/MM/YYYY para los chips de `_pdf_header()`
  - `_pdf_header()` — usa `_fmt_date_slash()` en vez de interpolar las fechas crudas
  - 10 funciones `_build_*_html()` nuevas (detalle, contratista, general, resumen-persona, resumen-horas, jornadas-trabajador, bono-mensual, hora-ponderada, detalle-tractorista, general-tractorista), extraídas de sus respectivos `download_tarjas_*_pdf` sin cambiar ninguna lógica de negocio — cada endpoint ahora llama a su builder y envuelve el resultado en el documento PDF completo
- `chatai/backend/controllers/reports_controller.py` — reescrito:
  - Importa `controllers.tarjas_controller as tc`; ya no duplica `_pdf_header`, `_fmt_clp`, `_fmt_date_display`, `_pivot_col_widths`, `_check_pivot_date_range`, `_hora_ponderada_9h`, `_PDF_CSS`, ni los 10 generadores por reporte
  - `_REPORT_GENERATORS` — cada entrada es un wrapper delgado que llama al builder compartido correspondiente con los kwargs correctos (los builders no comparten el mismo orden posicional de parámetros entre sí, así que los wrappers usan kwargs explícitos para evitar mezclar `empresa`/`contratista`)
  - `_html_resumen_tractorista` — se mantiene local (sin builder compartido posible), ahora usa `tc._pdf_header`/`tc._pdf_title`
  - `_EXTRA_BULK_CSS` — las 2 reglas que sí son exclusivas del documento combinado (`.page-break`, `.report-divider`) más las clases `.pivot-table`/`.col-*` que solo usa `_html_resumen_tractorista`

### Tests
- `chatai/tests/test_116_pdf_bulk_standalone_parity.py` — nuevo, 14 tests: para cada uno de los 10 reportes con PDF individual, verifica que `rc._REPORT_GENERATORS[id](...)` y `tc._build_*_html(...)` producen HTML idéntico contra la base de datos real; guarda de cobertura (ningún reporte puede agregarse a `_REPORT_GENERATORS` sin pasar por esta verificación, salvo `resumen-tractorista`); tests del fix de formato de fecha; test de `resumen-tractorista`.
- `chatai/tests/test_109_reportes_bulk_bono_hora_ponderada.py` — actualizado: las referencias a `rc._pdf_header`/`rc._html_bono_mensual`/`rc._html_hora_ponderada` (eliminadas) pasan a `tc._pdf_header`/`rc._REPORT_GENERATORS[...]`; las aserciones de texto se actualizan al nuevo formato de título (`_pdf_title`).
- `chatai/tests/test_112_hora_ponderada_bulk_parity.py` — actualizado: mismo cambio, más las constantes que antes se comparaban entre `rc`/`tc` (ahora no existen del lado de `rc`, se eliminaron esas comparaciones ya que la igualdad es estructural).
- `chatai/tests/test_54_pdf_titles_contratista.py` — el test de aislamiento que afirmaba que el PDF unificado nunca cambiaría sus títulos se actualizó para verificar lo contrario (delegación a los builders compartidos), documentando el cambio de decisión en su docstring.

## Routes
Sin cambios de rutas — mismos endpoints, mismo comportamiento observable salvo el formato de fecha (fix) y los títulos ahora consistentes.

## Tests
```
pytest tests/test_116_pdf_bulk_standalone_parity.py tests/test_109_reportes_bulk_bono_hora_ponderada.py tests/test_112_hora_ponderada_bulk_parity.py tests/test_54_pdf_titles_contratista.py -v
35 passed

pytest tests/ -q
274 passed, 2 failed (test_50_odoo_export_tractorista.py — preexistente, no relacionado)
```
Verificación visual manual (PDF → PNG, comparación lado a lado): "Hora Ponderada 9h" y "General Tractorista" — pixel-idénticos entre individual y unificado.

## Manual QA
1. En `/reportes`, descargar cada uno de los 10 reportes con PDF individual, solo ese reporte, con un contratista y rango de fechas conocidos.
2. Descargar el mismo reporte desde su página individual con los mismos filtros.
3. Comparar ambos PDFs — deben verse idénticos (mismo título "Tarjas-Reporte {Nombre}-{Contratista}", mismas fechas en formato DD/MM/YYYY, misma tabla, mismos valores).
4. Repetir para "Resumen tractorista" (sin individual) y confirmar que el título sigue el mismo formato que los demás.
