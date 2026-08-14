# Fix: PDF de Bonos Mensuales con columnas superpuestas
# Path: specs/117-fix-bono-mensual-pdf-columns/spec.md
issue: #117 · branch: 117-fix-bono-mensual-pdf-columns · date: 2026-08-14

## What
El PDF del reporte "Bonos Mensuales" (#100) se descargaba con las columnas RUT, Contratista, Empresa/Campo, CC y Fecha completamente superpuestas e ilegibles. Se corrige declarando anchos explícitos por columna en la tabla.

## Acceptance
- [x] El PDF de Bonos Mensuales se renderiza con las 8 columnas (Trabajador, RUT, Contratista, Empresa/Campo, CC, Fecha, Monto, Estado) correctamente separadas y legibles.
- [x] La fila "Suma total" del footer se ve igual de legible que las filas de datos.
- [x] El fix no depende de datos particulares (se prueba tanto con datos reales de julio 2026 como con nombres de contratista largos sintéticos).

## Context
- Módulo: `chatai/backend/controllers/tarjas_controller.py`, función `download_tarjas_bono_mensual_pdf` (línea ~3814), helpers `_build_bono_mensual_filters`, `_query_bono_mensual_rows`.
- Render PDF vía `xhtml2pdf`/`reportlab` (`_render_pdf`, línea ~428).
- **No es el mismo bug que #108** (issue #102, "Hora ponderada 9h"): ese reporte usaba `<table class="pivot-wide">` (`table-layout:fixed` + anchos inline por celda) y el bug era la fila de footer sin `style="width:...%"` rompiendo el layout de **toda** la tabla bajo `table-layout:fixed`.
- El reporte de Bonos Mensuales usa una tabla plana `<table>` (sin clase, sin `table-layout:fixed`, sin ningún ancho declarado en ninguna celda) — el mecanismo de reportlab/xhtml2pdf que falla acá es distinto: el algoritmo de **auto-ancho de columnas** (sin `colWidths` explícitos) de reportlab colapsa varias columnas (RUT/Contratista/Empresa-Campo/CC/Fecha) a un ancho casi nulo y superpone su texto, incluso sin `table-layout:fixed` y con datos reales completamente normales (nombres de contratista de 20-27 caracteres, nada extremo).
- Confirmado por reproducción real: se sirvió `download_tarjas_bono_mensual_pdf` directamente (bypasseando solo el bug preexistente y no relacionado de `strftime('%-d de %B de %Y')` en Windows, ya documentado en #100 — no se tocó ese código) contra los 6 registros reales de julio 2026 en `appsheet.tarjas_pagos`, se convirtió el PDF a PNG con `fitz` y se confirmó visualmente la superposición. Se reprodujo también con datos sintéticos idénticos en forma, descartando que dependiera de un valor particular.
- Se probó experimentalmente: agregar `style="width:X%"` a cada `<th>`/`<td>` (sin `table-layout:fixed`) resuelve el problema por completo — confirma que el fix correcto es el mismo patrón que ya usan otros reportes del archivo (`_pivot_col_widths`, tablas en líneas ~3252, ~3385, ~5090-5101, ~5181-5185), no necesariamente ligado a `table-layout:fixed`.

## Decisions
- Anchos elegidos (suman 100%): Trabajador 16%, RUT 11%, Contratista 20%, Empresa/Campo 14%, CC 7%, Fecha 9%, Monto 11%, Estado 12%. Se le da más espacio a Trabajador/Contratista/Empresa-Campo por ser los campos de texto libre más largos; CC y Fecha son los más angostos por contenido corto y predecible (código numérico / "DD mes AAAA").
- No se agregó `table-layout:fixed` ni la clase `pivot-wide` — la tabla no es un pivote de fechas y reproducir con anchos porcentuales simples ya es suficiente (confirmado en la verificación visual); mantener el layout auto de reportlab para el resto de columnas (ninguna, todas quedan con ancho explícito) no aporta nada acá.
- El footer ("Suma total") recibe los mismos `style="width:...%"` que las filas de datos en cada `<td>`, por consistencia y para evitar reintroducir el mecanismo de #108 si en el futuro alguien migra esta tabla a `table-layout:fixed`.
- No se tocó el bug preexistente de `strftime` en Windows (documentado en #100, no reproducible en producción/Linux).

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`: `download_tarjas_bono_mensual_pdf` — se agregó `style="width:...%"` a cada `<th>` del encabezado y a cada `<td>` de las filas de datos y de la fila de totales.

## Routes
Sin cambios de rutas.

## Tests
Verificado manualmente (mismo patrón que #100/#108, sin test unitario dedicado — ningún otro reporte de tarjas en `chatai/tests/` tiene test unitario propio de PDF):
- PDF renderizado vía llamada directa a `download_tarjas_bono_mensual_pdf(mes='2026-07')` contra la BD real (6 filas reales) → convertido a PNG con `fitz`, columnas correctamente separadas, sin superposición.
- Repetido con datos sintéticos de la misma forma → mismo resultado correcto.
- Footer "Suma total" verificado legible, mismo ancho de columnas que las filas de datos.

## Manual QA
1. Ir a Catálogo de Reportes → Tarjas → Contratistas → "Bonos Mensuales".
2. Seleccionar un mes con datos (ej. 2026-07) y hacer clic en "Consultar".
3. Descargar el PDF → las columnas Trabajador, RUT, Contratista, Empresa/Campo, CC, Fecha, Monto y Estado deben verse separadas y legibles, incluida la fila "Suma total".

## Deferred
- No se audita el resto de tablas planas del archivo (ej. `jornadas-trabajador`, 3 columnas) por el mismo bug — no reportado y con menos columnas, menor riesgo de colapsar el auto-layout de reportlab; queda fuera de alcance de este issue.
