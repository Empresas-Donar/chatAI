# Mostrar tabla por operador en pantalla y agregarla al PDF en orden de compra tractorista
# Path: specs/67-pivot-table-screen-pdf/spec.md
issue: #67 · branch: 67-pivot-table-screen-pdf · date: 2026-07-31

## What
En `/odoo/tarjas-tractorista`, la tabla "por operador" (fecha × trabajador — labor) que antes solo se podía descargar como Excel ahora también se muestra en pantalla (debajo de las tablas por CC) y se agrega como segunda tabla en el PDF descargable.

## Acceptance
- [x] Al generar la orden, aparece una nueva sección en pantalla debajo de las tablas por CC, con el pivote fecha × operador (mismo contenido que el Excel "Tabla por operador")
- [x] El PDF descargado incluye, además de la tabla plana actual, la tabla pivote por operador
- [x] La lógica de armado del pivote (query + pivot) no se duplica entre el endpoint de Excel, el nuevo endpoint JSON para pantalla, y el PDF
- [x] Tests de regresión

## Context
- Endpoint Excel existente: `GET /api/tarjas/tractorista/pivot-excel` (`tarjas_controller.py`) — antes construía el pivote con `pandas.pivot_table` directamente en el propio endpoint (lógica no reutilizable).
- Endpoint PDF existente: `GET /api/tarjas/tractorista/download-pdf` — tabla plana fecha→trabajador→labor con subtotales por día; no traía el pivote.
- Pantalla: `purchase_orders_tractorista.html` / `.js` — solo renderizaba las tablas por CC (`#cc-sections`) desde `/api/tarjas/tractorista/preview`.
- Este repo ya tenía un patrón de guard para pivotes anchos en PDF (`_check_pivot_date_range`, `_pivot_col_widths`, issue #52) — reutilizado aquí aplicándolo al número de columnas de operador (no de fechas, que es el eje ancho en el pivote original de #52; en este pivote el eje que puede crecer es el de operadores/labores, no las fechas).

## Decisions
- Se extrajeron dos helpers compartidos: `_fetch_tractorista_pivot_rows(conn, contratista, campo, fecha_inicio, fecha_termino, cc=None)` (query SQL) y `_build_tractorista_pivot(rows)` (dict con `dates`, `columns`, `matrix`, `col_totals`, `date_totals`, `grand_total`). Los tres consumidores (Excel, JSON preview, sección PDF) llaman a los mismos dos helpers — ya no pueden desincronizarse entre sí.
- Se reescribió `pivot_tarjas_tractorista_excel` para usar estos helpers en vez de `pandas.pivot_table`, eliminando la dependencia de pandas en este endpoint. Efecto secundario positivo: el pivote anterior ordenaba las fechas como texto `"%d/%m/%Y"` (orden alfabético, no cronológico — un rango que cruce de mes, ej. 31/07 y 05/08, quedaba mal ordenado); ahora se ordena por fecha ISO antes de formatear para mostrar.
- Nuevo endpoint `GET /api/tarjas/tractorista/pivot-preview` (JSON) — mismo shape que devuelve `_build_tractorista_pivot`, consumido por el JS para renderizar la tabla en pantalla automáticamente después de "Generar orden" (no requiere un botón adicional).
- El PDF (`download_tarjas_tractorista_pdf`) ya soportaba un filtro opcional `cc`; se extendió `_fetch_tractorista_pivot_rows` con el mismo filtro `cc` para que, si el PDF se pide filtrado por centro de costo, la tabla por operador quede scoped al mismo CC (no muestre todo el contratista/campo).
- Se renombró la variable interna de escape a `_escape_html` (helper propio, sin usar el módulo estándar `html`) porque **todas** las funciones de generación de PDF en este archivo usan una variable local llamada `html` para el string final (`html = f"""<!DOCTYPE ...`) — importar el módulo `html` a nivel de archivo rompía esas funciones con `NameError: cannot access free variable 'html'` (Python trata `html` como local en toda la función una vez que se le asigna en cualquier punto de ella).
- Se aplicó `_check_pivot_date_range` (reutilizado tal cual, aunque su nombre sugiere fechas) sobre `pivot["columns"]` — la función solo revisa `len(lista) > MAX_PIVOT_DATES`, así que reutilizarla para la lista de columnas de operador es válido y evita duplicar el guard.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_escape_html()` — helper nuevo, evita colisión con la convención local `html = f"""..."""` usada en todo el archivo.
  - `_fetch_tractorista_pivot_rows()` — helper nuevo, query compartida (antes duplicada entre pivot-excel y download-pdf).
  - `_build_tractorista_pivot()` — helper nuevo, arma el pivote (fechas × columnas × matriz × totales).
  - `preview_tarjas_tractorista_pivot` (`GET /api/tarjas/tractorista/pivot-preview`) — endpoint nuevo, JSON para la pantalla.
  - `pivot_tarjas_tractorista_excel` (`GET /api/tarjas/tractorista/pivot-excel`) — reescrito para usar los helpers compartidos en vez de pandas.
  - `download_tarjas_tractorista_pdf` (`GET /api/tarjas/tractorista/download-pdf`) — se agregó una segunda tabla ("Tabla por operador") al HTML antes de renderizar el PDF.

### Frontend
- `chatai/frontend/templates/purchase_orders_tractorista.html` — nuevo `<div id="pivot-section">` debajo de `#cc-sections`.
- `chatai/frontend/static/purchase_orders_tractorista.js` — `loadPivotTable()` / `renderPivotTable()` nuevos, invocados automáticamente tras un "Generar orden" exitoso; reutiliza las clases CSS `.cc-section` / `.oc-table` ya existentes (sin CSS nuevo).

### Tests
- `chatai/tests/test_67_pivot_table_screen_pdf.py` — 7 tests: helper de pivote (matriz/totales, caso vacío), el nuevo endpoint JSON coincide internamente (matrix suma a los totales), el Excel sigue funcionando tras el refactor (deja de depender de pandas), el PDF renderiza con la sección nueva, el filtro `cc` scopea también el pivote del PDF, isolation (general-tractorista no se vio afectado).

## Routes
| Method | Path | Nota |
|--------|------|------|
| GET | /api/tarjas/tractorista/pivot-preview | **Nuevo** — JSON del pivote por operador para la pantalla |
| GET | /api/tarjas/tractorista/pivot-excel | Sin cambio de contrato, reescrito internamente |
| GET | /api/tarjas/tractorista/download-pdf | Ahora incluye una segunda tabla (por operador) en el PDF |

## Tests
```
pytest tests/test_67_pivot_table_screen_pdf.py -v
7 passed in 6.42s

pytest tests/ -v
184 passed, 2 failed in 19.53s
```
Los 2 fallos (`test_50_odoo_export_tractorista.py`) son preexistentes en `main`, no relacionados con este fix (mismo hallazgo que en issue #64).

Cross-farm isolation: ✅ (`test_67_general_tractorista_pdf_unaffected_isolation`)

## Manual QA
1. En `/odoo/tarjas-tractorista`, generar una orden para Ramón Díaz / Talagante / 01-31 julio 2026 → debe aparecer, debajo de las tablas por CC, una nueva sección "Tabla por operador" con una fila por fecha y una columna por trabajador — labor.
2. Descargar el PDF ("Descargar PDF") → debe traer, después de la tabla plana fecha→trabajador→labor, una segunda tabla con el mismo pivote por operador.
3. Descargar "Tabla por operador (Excel)" y comparar contra la tabla en pantalla y la del PDF → los tres deben mostrar exactamente los mismos montos.

## Deferred
- No se agregó un guard de "demasiadas columnas de operador" con mensaje propio (se reutilizó `_check_pivot_date_range` tal cual); en la práctica cada contratista tiene 2-5 tractoristas, por lo que el riesgo de overflow de ancho es bajo. Si en el futuro un contratista tuviera muchos más operadores, convendría un mensaje de error más específico ("demasiados operadores" en vez de "demasiadas fechas").
