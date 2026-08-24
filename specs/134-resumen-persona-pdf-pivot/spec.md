# PDF de Resumen por Persona debe usar formato pivot (una columna por fecha)
# Path: specs/134-resumen-persona-pdf-pivot/spec.md
issue: #134 · branch: 134-resumen-persona-pdf-pivot · date: 2026-08-24

## What
El PDF de "Resumen por persona" ahora usa el mismo formato pivot que la pantalla: una fila por trabajador/tipo de pago, una columna por cada fecha del rango consultado, y una columna Total al final — en vez del listado plano anterior (una fila por trabajador+fecha, con subtotales).

## Acceptance
- [x] Cada fecha del rango es su propia columna en el PDF, igual que en pantalla
- [x] El trabajador aparece una sola vez por tipo de pago (no repetido por cada fecha)
- [x] Rangos de fechas muy amplios siguen rechazándose con un error claro en vez de romper el layout
- [x] El PDF unificado de `/reportes` hereda el mismo cambio (comparten código desde el issue #116)

## Context
- El usuario compartió una captura de la pantalla "Resumen por trabajador" y pidió que el PDF quedara igual: "debe ser cada fecha una columna".
- El código tenía un comentario que decía "xhtml2pdf cannot reliably render wide pivot tables" — ya no es cierto: "Detalle Contratistas", "Horas Extra" y "Hora Ponderada 9h" ya usan pivots de fecha exitosamente vía `_pivot_col_widths()` (issues #52, #132). Se aplicó el mismo patrón ya probado.
- Este endpoint tampoco incluía `_PDF_CSS` en su documento — a diferencia de todos los demás PDFs de tarjas, solo tenía su propio header oscuro (`background:#1e293b`) con una tabla `border="1"` sin ninguna clase de estilo compartida. Se agregó `_PDF_CSS` para poder usar `.pivot-wide`, manteniendo el header oscuro tal cual estaba (el usuario no pidió cambiarlo, solo la estructura de la tabla).
- No se replicó el tema de color naranja/crema exacto de la pantalla — el PDF usa la paleta gris/blanca compartida por el resto de los PDFs de tarjas, consistente con cómo los otros reportes con pivot en pantalla (ej. Horas Extra) tampoco clonan el color exacto de su pantalla en el PDF. El pedido explícito del usuario ("es decir debe ser cada fecha una columna") apunta a la estructura, no al color.

## Decisions
- Ancho de columnas: `_pivot_col_widths({"worker": 18, "tipo": 9, "total": 11}, len(dates))` — mismo patrón que Horas Extra, sin columna de "monto" separada (acá el total YA es dinero, a diferencia de Horas Extra que tiene horas + monto por separado).
- Celdas en 0 muestran "0" (no vacío), igual que la pantalla.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_build_resumen_persona_html()` — reescrito de lista plana a pivot por fecha
  - `download_tarjas_resumen_persona_pdf()` — agrega `<style>{_PDF_CSS}</style>` al documento (antes ausente)

### Tests
- `chatai/tests/test_134_resumen_persona_pdf_pivot.py` — 5 tests contra la base de datos real: estructura pivot (columnas de fecha, sin "Subtotal"/"Fecha"/"Monto" del layout viejo), trabajador aparece una sola vez, PDF renderiza con las columnas de fecha esperadas, rango amplio se rechaza limpio, y paridad con el generador del PDF unificado (`reports_controller.py`).

## Routes
Sin cambios de rutas.

## Tests
```
pytest tests/test_134_resumen_persona_pdf_pivot.py -v
5 passed

pytest tests/ -q
308 passed, 2 failed (test_50_odoo_export_tractorista.py — preexistente, no relacionado)
```
Verificación visual manual (PDF → PNG): coincide con la captura de pantalla compartida por el usuario — mismas filas, mismos valores, cada fecha como columna.

## Manual QA
1. Descargar el PDF de "Resumen por persona" con un rango de 1-2 semanas — confirmar que hay una columna por cada fecha, igual que en pantalla.
2. Confirmar que cada trabajador aparece una sola vez (no una fila por cada fecha).
3. Descargar el mismo reporte desde el PDF unificado de `/reportes` — debe verse idéntico.
