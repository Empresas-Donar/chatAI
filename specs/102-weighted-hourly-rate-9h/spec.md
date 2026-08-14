# Nuevo reporte: Hora ponderada estandarizada a 9 horas
# Path: specs/102-weighted-hourly-rate-9h/spec.md
issue: #102 · branch: 102-weighted-hourly-rate-9h · date: 2026-08-14

## What
Nuevo reporte "Hora ponderada estandarizada a 9 horas" en Catálogo de Reportes → Tarjas → Contratistas: tabla pivote Labor→CC × Fecha donde cada celda proyecta cuánto se habría ganado por hora si la jornada de esa combinación hubiese sido de 9 horas completas, en vez de las horas realmente trabajadas.

## Acceptance
- [x] Nueva entrada "Hora ponderada estandarizada a 9 horas" en Catálogo de Reportes → Tarjas → Contratistas.
- [x] Tabla pivote: filas = Labor, luego CC dentro de cada Labor (agrupado/ordenado Labor → CC); columnas = una por cada fecha distinta dentro del rango seleccionado.
- [x] Cada celda muestra `hora_ponderada_9h` para la combinación Labor+CC+Fecha correspondiente — no el monto bruto ganado ese día.
- [x] Filtros: rango de fechas (Desde/Hasta), contratista, empresa, centro de costo, labor.
- [x] Mismas acciones que el resto de reportes de Tarjas: Consultar (pantalla), descarga Excel, descarga PDF — mismo look and feel.
- [x] Cuando `horas_trabajadas` es 0/NULL en una celda, se muestra `-`.

## Context
- Este repo NO usa SQLAlchemy/Alembic/Pydantic — los controllers ejecutan SQL crudo con psycopg2 directo contra PostgreSQL (`chatai/backend/controllers/tarjas_controller.py`). Se siguió ese patrón, no el genérico de la playbook.
- Concepto "valor calculado por hora" (`costo_hora`) ya existe en el reporte Detalle Operacional: `_query_detalle_rows` (`tarjas_controller.py:721-750`), formula `ROUND(SUM(total_labor) / SUM(horas_trabajadas), 0)`, sobre la vista `appsheet.tarjas_reporte` con columnas `"Nombre Labor"` / `"CC"`.
- Patrón pivote de referencia: `tarjas_contratista` (Por persona operacional) — page+filters+data en `tarjas_controller.py:1014-1125`, pivote client-side en `tarjas_contractor.js:renderPivot()` (líneas 125-250), export Excel en `download_tarjas_contratista_excel` (`tarjas_controller.py:2132`) y PDF en `download_tarjas_contratista_pdf` (`tarjas_controller.py:3085`), ambos con pivote por fecha construido en Python (mismo patrón usado acá).
- Se optó por consultar directamente `appsheet.tarjas_pagos` (no la vista `tarjas_reporte`) porque el patrón pivote necesita filas crudas por fecha para pivotear en el cliente — igual que `tarjas_contratista`, que también lee `tarjas_pagos` directo. Columnas usadas: `labor`, `cuartel_cc`, `total_trabajado`, `horas_trabajadas`, `fecha`, `contratista`, `nombre_campo`, `tipo_pago` (nombres exactos AppSheet, sin renombrar).
- Skeleton de referencia para una feature nueva completa (rutas, forma del spec, entrada de nav): Bonos Mensuales — `specs/100-contractor-monthly-bonus-report/spec.md` y `tarjas_controller.py:3608-3805` (`tarjas_bono_mensual_page` y rutas asociadas).
- Nav: `chatai/frontend/templates/base.html`, lista `nav_menu` → Catálogo de Reportes → Tarjas → Contratistas (mismo submenu que Bonos mensuales, Jornadas por trabajador, etc.).
- CSS del pivote reutilizado tal cual: `chatai/frontend/static/tarjas_contractor.css` (clases `.tc-pivot`, `.cell-value`, `.tc-totals-row`, etc. son genéricas, no dependen del texto "trabajador").

## Decisions
- **Agrupación de fila = Labor + CC** (no trabajador). La fórmula pedida es por combinación Labor+CC+Fecha, agregando todos los trabajadores/contratistas que caen en esa celda dentro de los filtros aplicados — coherente con que "costo_hora" en Detalle Operacional también se agrega a nivel Labor+CC, no a nivel de trabajador individual.
- **Filtros de Labor y Centro de Costo se mantienen expuestos en la UI** aunque ya son las dimensiones de fila del pivote — siguiendo el mismo precedente ya usado en `tarjas_contratista`, que expone `centro_costo`/`labor` como filtros pese a que también son columnas de agrupación. Permite acotar el pivote (menos filas) sin cambiar su forma.
- **Ninguna celda "Total" (columna derecha por fila, ni la fila de totales del footer — por columna de fecha o en su celda derecha) es la suma de los valores `hora_ponderada_9h` ya proyectados.** Sumar un valor por-hora proyectado a través de celdas independientes no tiene significado económico (es promediar promedios). En su lugar, igual que la columna "Costo/hr" ya existente en `tarjas_contratista` (que se recalcula desde las sumas agregadas, nunca sumando columnas de fecha), cada una de estas celdas recalcula `ROUND(SUM(total_trabajado) / SUM(horas_trabajadas) * 9, 0)` sobre las sumas agregadas correspondientes en vez de sumar celdas ya proyectadas:
  - Columna Total de cada fila: agrega `total_trabajado`/`horas_trabajadas` de TODO el rango de fechas para esa fila (Labor+CC).
  - Footer por columna de fecha: agrega `total_trabajado`/`horas_trabajadas` de TODAS las filas (todas las Labor+CC) para esa fecha — un valor blended del día.
  - Footer columna Total (celda inferior derecha, "Hora ponderada 9h global"): agrega `total_trabajado`/`horas_trabajadas` de TODO el dataset filtrado — un único valor de referencia.
  Se documenta explícitamente porque mezclar distintas Labores (y, en el footer por fecha, distintos CC) en un solo valor blended es una simplificación — labores con jornales muy distintos se promedian juntas. Si en el futuro se pide desglosar el total por Labor en vez de un único blended global, es un cambio de UI, no de backend (el backend ya expone las filas crudas por Labor+CC+Fecha).
- Se reutiliza `appsheet.tarjas_pagos` en vez de `appsheet.tarjas_reporte` para mantener el mismo endpoint de filtros/datos crudos que `tarjas_contratista` (misma tabla, mismos 4 niveles de fallback ya resueltos en la vista no son necesarios aquí porque no se muestra `codigo_labor` ni datos Odoo, solo el pivote Labor/CC/Fecha).

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`: rutas `tarjas_hora_ponderada_page`, `get_tarjas_hora_ponderada_filters`, `get_tarjas_hora_ponderada_data`, `download_tarjas_hora_ponderada_excel`, `download_tarjas_hora_ponderada_pdf`.

### Frontend
- `chatai/frontend/templates/tarjas_hora_ponderada.html` (nuevo)
- `chatai/frontend/static/tarjas_hora_ponderada.js` (nuevo)
- `chatai/frontend/templates/base.html`: nueva entrada de nav bajo Tarjas → Contratistas.

## Routes
| Method | Path | Description |
|--------|------|-------------|
| GET | /tarjas/hora-ponderada-9h | Página del reporte |
| GET | /api/tarjas/hora-ponderada-9h/filters | Contratistas/empresas/centros de costo/labores distintos en `tarjas_pagos` |
| GET | /api/tarjas/hora-ponderada-9h | Filas crudas filtradas (mismo patrón que `/api/tarjas/contratista`) para pivotear en el cliente |
| GET | /api/tarjas/hora-ponderada-9h/download-excel | Descarga Excel (pivote Labor→CC × Fecha) |
| GET | /api/tarjas/hora-ponderada-9h/download-pdf | Descarga PDF (mismo pivote) |

## Tests
Verificado manualmente contra la BD de desarrollo real (sin mocks, según convención del repo para reportes de Tarjas — ningún reporte de este módulo tiene test unitario dedicado en `chatai/tests/`, incluido Bonos Mensuales #100).

## Manual QA
1. Ir a Catálogo de Reportes → Tarjas → Contratistas → "Hora ponderada estandarizada a 9 horas".
2. Seleccionar un rango de fechas con datos conocidos y hacer clic en "Consultar" → deben aparecer filas agrupadas por Labor, con sub-filas de CC dentro de cada Labor, y una columna por fecha.
3. Verificar manualmente una celda: tomar `SUM(total_trabajado)` y `SUM(horas_trabajadas)` para una combinación Labor+CC+Fecha específica en `appsheet.tarjas_pagos`, calcular `ROUND(SUM(total_trabajado)/SUM(horas_trabajadas)*9, 0)` y confirmar que coincide con el valor mostrado en la celda.
4. Confirmar que una celda con `horas_trabajadas` 0 o NULL muestra `-`.
5. Filtrar por Labor y por Centro de Costo por separado → confirmar que acotan correctamente las filas del pivote.
6. Con datos en pantalla, hacer clic en "Excel" y "PDF" → ambos deben descargar con el mismo pivote Labor→CC × Fecha visto en pantalla.

## Deferred
- No se agrega esta vista al selector de descarga masiva de PDFs (`/reportes`) — mismo alcance que Bonos Mensuales (#100), el pedido fue específicamente por la entrada en Catálogo de Reportes.
- No se desglosa el total del footer por Labor (queda como un único valor blended sobre todas las filas) — ver Decisions.
