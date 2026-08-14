# PDF unificado de Hora Ponderada 9h no coincide con el PDF individual
# Path: specs/112-hora-ponderada-bulk-parity/spec.md
issue: #112 · branch: 112-hora-ponderada-bulk-parity · date: 2026-08-14

## What
La sección "Hora ponderada 9h" del PDF unificado (`/reportes`) ahora se comporta exactamente igual que el PDF individual (`/tarjas/hora-ponderada-9h/download-pdf`): mismo highlighting de valores altos, mismo límite de rango de fechas, y misma protección de layout.

## Acceptance
- [x] Las celdas diarias con `hora_ponderada_9h > $30.000` se resaltan igual en ambos PDFs (fondo naranja, texto en negrita)
- [x] El rango de fechas se limita a 23 días en ambos, con el mismo mensaje de error sugiriendo Excel
- [x] La fila de totales (footer) no rompe el layout de la tabla en rangos de fechas anchos
- [x] Los valores numéricos calculados son idénticos entre ambos PDFs para los mismos filtros

## Context
- El generador `_html_hora_ponderada` de `reports_controller.py` (issue #109) se escribió ANTES de que el issue #108 arreglara el PDF individual. Cuando el fix de #108 se mergeó (PR #111) justo después de mi PR #109, el unificado quedó desactualizado — nadie lo tocó a propósito, fue una carrera entre dos ramas trabajando en el mismo archivo en paralelo sin overlap de código.
- Bug real que traía el unificado (mismo tipo que #108, no solo estético): la fila de totales (`footer_val`) armaba celdas `<td></td>` vacías, sin el `style="width:...%"` que sí llevan las demás filas. Ese fue exactamente el root cause del bug de #108 — a xhtml2pdf le basta con que UNA fila de la tabla no tenga el ancho explícito para romper el layout de TODA la tabla en `table-layout:fixed`.
- El unificado tampoco tenía el límite de 23 fechas (`MAX_PIVOT_DATES_HORA_PONDERADA`), así que un rango amplio podía generar el mismo tipo de tabla rota que #108 documentó, en vez de redirigir a Excel con un error amigable.
- `reports_controller.py` no importa nada de `tarjas_controller.py` (convención ya establecida — cada uno duplica sus propios helpers de PDF). Se duplicaron `_pivot_col_widths()`, `_check_pivot_date_range()`, `HORA_PONDERADA_HIGHLIGHT_THRESHOLD` y `MAX_PIVOT_DATES_HORA_PONDERADA` en `reports_controller.py`, con los mismos valores y misma lógica.
- **Bonos mensuales** (la otra mitad de #109) no tenía brechas equivalentes — su PDF individual no tiene highlighting ni pivot de fechas, así que no había nada que portar ahí.

## Decisions
- Se prefirió duplicar los helpers (siguiendo la convención ya usada en el archivo) en vez de importar cruzando controllers — evita acoplar dos módulos que hasta ahora eran independientes, a costa de tener que mantener la duplicación sincronizada manualmente (riesgo ya aceptado en el resto del archivo).
- La tabla pasó de la clase `pivot-table` (ancho por columna en `%` fijo vía CSS, la misma que usan `resumen-horas`/`resumen-persona` en este archivo) a `pivot-wide` con anchos inline calculados por `_pivot_col_widths()` — igual que el PDF individual — porque los valores en pesos de este reporte pueden ser mucho más anchos que horas o texto corto, y es lo que #108 verificó que funciona sin romper el layout.

## Implemented
### Backend
- `chatai/backend/controllers/reports_controller.py`:
  - `_pivot_col_widths()` — helper nuevo, duplicado de `tarjas_controller.py`
  - `_check_pivot_date_range()` — helper nuevo, duplicado de `tarjas_controller.py`
  - `_HORA_PONDERADA_HIGHLIGHT_THRESHOLD` / `_MAX_PIVOT_DATES_HORA_PONDERADA` — constantes nuevas, mismos valores que `tarjas_controller.py`
  - `_html_hora_ponderada()` — reescrito para usar `_pivot_col_widths`, highlighting inline, límite de fechas, y anchos explícitos en la fila de totales
  - `_PDF_CSS` — nueva clase `.pivot-wide` (igual a la de `tarjas_controller.py`)

### Tests
- `chatai/tests/test_112_hora_ponderada_bulk_parity.py` — 4 tests contra la base de datos real: mismas constantes que el standalone, mismo error al superar 23 días, highlighting presente para valores reales > $30.000 (contratista SERVICIOS AGRICOLAS RD SPA), todas las celdas del footer llevan `style` explícito, y los valores calculados coinciden entre el PDF unificado y el individual para los mismos filtros.
- `chatai/tests/test_109_reportes_bulk_bono_hora_ponderada.py` — actualizado: los rangos de fecha usados para "hora-ponderada-9h" se acotaron a ≤23 días (antes usaban 41, que ahora correctamente dispara el error de rango); la aserción sobre la clase CSS vieja (`col-worker`) se cambió por `pivot-wide`.

## Routes
Sin cambios de rutas.

## Tests
```
pytest tests/test_112_hora_ponderada_bulk_parity.py tests/test_109_reportes_bulk_bono_hora_ponderada.py -v
12 passed in 7.37s

pytest tests/ -q
260 passed, 2 failed (test_50_odoo_export_tractorista.py — preexistente, no relacionado)
```

## Manual QA
1. En `/reportes`, seleccionar solo "Hora ponderada 9h" con un rango de fechas que incluya valores altos (ej. tractoristas) → las celdas por sobre $30.000 deben verse resaltadas en naranja, igual que en `/tarjas/hora-ponderada-9h` → Descargar PDF.
2. Elegir un rango de más de 23 días → debe fallar con el mismo mensaje de error que el PDF individual, sugiriendo Excel.
3. Descargar el PDF individual y el unificado con los mismos filtros → comparar que los números por Labor/CC/fecha sean idénticos.
