# Ocultar trabajadores sin horas extra en el reporte "Horas extra por persona"
# Path: specs/97-resumen-horas-filter-zero/spec.md
issue: #97 · branch: 97-resumen-horas-filter-zero · date: 2026-08-14

## What
El reporte "Detalle trabajador hora extra" (`/tarjas/resumen-horas`, también conocido como "Horas extra por persona") mostraba en pantalla, Excel y PDF a **todos** los trabajadores con algún registro de pago en el rango de fechas consultado, aunque su suma de `horas_extras` en ese período fuera 0. Ahora solo se muestran los trabajadores cuyo total de horas extra en todo el período consultado es mayor a 0. Se agregó una nota explicativa en pantalla y en el PDF: *"Sólo se muestran aquellos trabajadores que cuentan con horas extras en el periodo especificado."*

## Acceptance
- [x] Pantalla, Excel y PDF excluyen a los trabajadores cuyo total de horas extra del período es 0
- [x] Un trabajador con horas extra en algunos días del período pero no en otros sigue apareciendo completo, incluyendo sus días en 0 (el filtro es por trabajador/total del período, no fila por fila)
- [x] Se muestra la nota explicativa en pantalla (bajo el subtítulo) y en el PDF (bajo el encabezado)
- [x] El filtro respeta el scoping por contratista (un trabajador con horas extra para un contratista no "contamina" el resultado de otro contratista)

## Context
- Los 3 endpoints detrás de este reporte hacen cada uno su propia query SQL y agrupación en Python, sin código compartido: `get_tarjas_resumen_horas` (pantalla), `download_tarjas_resumen_horas_excel`, `download_tarjas_resumen_horas_pdf` — todos en `chatai/backend/controllers/tarjas_controller.py`.
- La query base usa `COALESCE(SUM(horas_extras), 0)`, así que cualquier trabajador con un registro de pago en el rango de fechas aparecía con horas en 0 en vez de no aparecer.
- **Incidente durante el desarrollo (no relacionado al fix):** este trabajo se ejecutó por error en el mismo checkout compartido donde había una sesión en paralelo trabajando en el issue #96 (mismo archivo `tarjas_controller.py`). Se detectó la colisión, se aisló el trabajo del issue #97 en un git worktree separado (`.claude/worktrees/issue-97-resumen-horas`) sin tocar ni perder el trabajo del issue #96, que siguió su curso normal en el checkout principal (commit `0d81c46`). El diff final de este spec es exclusivamente el fix de horas extra, verificado línea por línea contra el commit base.

## Decisions
- El filtro se calcula agregando el total de `horas_extras` por trabajador (sumando todos los `tipo_pago` y fechas del período) y se excluye al trabajador solo si ese total es 0 — nunca se filtra fila por fila, para no ocultar los días en 0 de un trabajador que sí tuvo horas extra en otros días del mismo período.
- El endpoint de pantalla (`get_tarjas_resumen_horas`) filtra sobre `rows` antes de devolver la respuesta JSON (la agrupación por trabajador/tipo_pago la sigue haciendo el frontend en `tarjas_resumen_horas.js`); Excel y PDF filtran sobre el dict `workers` ya agrupado en Python, después de construirlo y antes de ordenarlo.
- Nota agregada como párrafo `.trp-note` en pantalla (bajo el subtítulo del `page-header`) y como `<p class="pdf-note">` en el PDF (bajo `_pdf_header()`, antes de la tabla), con estilo discreto (itálica, gris) consistente con el resto del CSS de cada superficie.
- No se tocó el reporte de "resumen-persona-tractorista" ni otros reportes de tarjas — el pedido fue específico a "horas extra por persona".

## Implemented
### Controllers
- `chatai/backend/controllers/tarjas_controller.py`:
  - `_PDF_CSS` — nueva clase `.pdf-note`
  - `get_tarjas_resumen_horas()` — filtra `rows` por total de horas extra > 0 por trabajador antes de devolver la respuesta
  - `download_tarjas_resumen_horas_excel()` — filtra el dict `workers` por total de horas extra > 0 por trabajador antes de ordenar
  - `download_tarjas_resumen_horas_pdf()` — mismo filtro que Excel; agrega el párrafo de nota explicativa al HTML del PDF

### Frontend
- `chatai/frontend/templates/tarjas_resumen_horas.html` — párrafo `.trp-note` con el texto explicativo, bajo el subtítulo del reporte
- `chatai/frontend/static/tarjas_resumen_persona.css` — estilo `.trp-note`

### Tests
- `chatai/tests/test_97_resumen_horas_hide_zero_workers.py` — 7 tests contra la base de datos real (contratista `HERBI ML SPA`, 46 trabajadores en el rango de prueba, solo 4 con horas extra > 0): exclusión en pantalla, preservación de días en 0 para un trabajador con horas mixtas, exclusión en Excel, exclusión y nota en PDF, nota en el template HTML, y aislamiento por contratista (scoping cruzado).

## Routes
Sin cambios de rutas — mismo comportamiento de filtros existente, solo cambia qué filas se incluyen en la respuesta.

## Tests
```
pytest tests/test_97_resumen_horas_hide_zero_workers.py -v
7 passed in 6.33s
```

## Manual QA
1. Ir a `/tarjas/resumen-horas`, filtrar por un contratista y un rango de fechas con trabajadores mixtos (con y sin horas extra) → solo deben listarse los trabajadores con horas extra > 0 en el total, y debe verse la nota explicativa bajo el subtítulo.
2. Descargar el Excel del mismo filtro → mismas filas que en pantalla, sin trabajadores en 0.
3. Descargar el PDF del mismo filtro → mismas filas, más la nota explicativa visible bajo el encabezado.
