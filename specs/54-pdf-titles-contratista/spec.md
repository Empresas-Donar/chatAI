# Agregar nombre del contratista al título de los PDFs de tarjas
# Path: specs/54-pdf-titles-contratista/spec.md
issue: #54 · branch: 54-pdf-titles-contratista · date: 2026-07-29

## What
Los 8 PDFs individuales de tarjas (los que se descargan desde cada página de reporte, no el bulk-PDF de `/reportes`) ahora muestran el nombre del contratista en el título cuando se filtra por uno, formato `Tarjas-Reporte {Nombre del reporte}-{Contratista}` (ej. `Tarjas-Reporte Detalle Contratistas-Herbi Ml Spa`).

## Acceptance
- [x] Los PDFs muestran el nuevo formato de título cuando se filtra por contratista
- [x] El nombre del contratista se capitaliza (`HERBI ML SPA` → `Herbi Ml Spa`)
- [x] Sin filtro de contratista, el título no incluye el sufijo

## Context
- **Primera vuelta (incompleta):** se acotó el alcance a 4 reportes (`contratista`, `detalle-tractorista`, `general-tractorista`, `resumen-horas`), asumiendo que eran los únicos con filtro de contratista.
- **Corrección del usuario:** todos los PDFs de tarjas individuales aceptan `contratista` como parámetro — se habían omitido `general`, `detalle`, `resumen-persona` y `jornadas-trabajador`. Verificado revisando cada función: los 8 endpoints (`/api/tarjas/*/download-pdf` en `tarjas_controller.py`) tienen `contratista: str = Query(None)`.
- Regla de nombre confirmada: nombre completo capitalizado con `.title()` (no solo la primera palabra).
- `resumen-persona` no usa `_pdf_header()` — arma su propio header HTML en línea (tabla con fondo oscuro). Se actualizó igual, inyectando el resultado de `_pdf_title()` en el `<b>` del título.

## Decisions
- Etiqueta por reporte (definida una por una, sin una fuente única de la que derivarlas todas):
  - `contratista` → "Detalle Contratistas"
  - `detalle-tractorista` → "Detalle Tractoristas"
  - `general-tractorista` → "General Tractoristas"
  - `resumen-horas` → "Horas Extra"
  - `general` → "General Operacional"
  - `detalle` → "Detalle Operacional"
  - `jornadas-trabajador` → "Jornadas Por Trabajador"
  - `resumen-persona` → "Resumen Por Persona"
- El bulk-PDF de `/reportes` (`reports_controller.py`, feature separada — descarga múltiples reportes combinados en un solo PDF) queda **fuera de alcance** — sus títulos estáticos ("General — Tarjas Contratistas", etc.) no se tocaron.

## Implemented
### Controllers
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_pdf_title()` — helper, arma `"Tarjas-Reporte {report_name}-{contratista.title()}"` (o sin sufijo si no hay contratista)
  - 8 llamadas de título actualizadas (7 vía `_pdf_header()`, 1 vía header inline en `resumen-persona`)

### Tests
- `chatai/tests/test_54_pdf_titles_contratista.py` — 9 tests: capitalización, título sin contratista, string vacío, las 8 etiquetas correctas, isolation check (bulk-PDF de `/reportes` sin tocar), y 4 tests de integración real (PDF generado + texto extraído) para los reportes agregados en la segunda vuelta

## Routes
Sin cambios de rutas — solo el texto del título dentro de los PDFs ya existentes.

## Tests
```
pytest tests/test_54_pdf_titles_contratista.py -v
9 passed in 4.39s

pytest tests/ -v
163 passed in 14.82s
```
Cross-farm isolation: ✅ (test_54_cross_report_isolation_bulk_pdf_titles_unchanged)

## Manual QA
1. Descargar el PDF de "Detalle contratista" filtrando por HERBI ML SPA → título "Tarjas-Reporte Detalle Contratistas-Herbi Ml Spa".
2. Descargar "General" (operacional) filtrando por un contratista → título "Tarjas-Reporte General Operacional-{Contratista}".
3. Repetir para los 6 reportes restantes (Detalle, Detalle tractorista, General tractorista, Horas extra, Jornadas por trabajador, Resumen por persona) y sin filtro de contratista en cada uno (el título no debe llevar sufijo).
