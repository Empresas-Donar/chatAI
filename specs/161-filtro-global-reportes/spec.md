# Spec: Filtro global de empresa, contratista y fechas

**Issue:** #161
**Branch:** `161-filtro-global-reportes`

## What

Barra de filtros globales (Empresa, Contratista, Fecha de Inicio, Fecha de Fin) en el chrome, visible en páginas de reportes. Los valores persisten al navegar entre reportes vía localStorage (canónico) y query params de URL (enlaces compartidos). Los cuatro campos se quitan de cada `.filter-bar` local.

Los filtros específicos de cada reporte (CC, labor, campo, tipo, trabajador, etc.) viven en un modal **Filtros avanzados**; el botón Consultar/Generar de cada página queda en la barra global.

## Acceptance Criteria

- Barra global sticky bajo el navbar, visible en `/tarjas`, `/dashboard`, `/reportes`, `/odoo`, `/despacho`
- No visible en Chat IA, Sensores, Utilidades, login
- Cuatro controles: Empresa (`fil-empresa`, "Todas"), Contratista (`fil-contratista`, "Todos"), Fecha de Inicio (`fil-from`), Fecha de Fin (`fil-to`)
- Persistencia: localStorage (canónico) + URL query params (URL gana al cargar por clave)
- Al cambiar un filtro global se guarda de inmediato en localStorage
- Al navegar entre reportes (y al cambiar Empresa / Contratista / fechas) la consulta corre sola; no hay que pulsar Consultar. El botón queda para filtros avanzados del modal.
- OC y facturación se auto-generan solo si ya hay empresa + contratista + fechas. Notas de crédito siguen pidiendo Generar.
- Fechas por defecto: lunes–domingo de la semana actual si no hay valores guardados
- Los 4 campos se quitan de las barras locales de cada reporte
- `fil-mes` de bono mensual se mantiene como filtro de página; se hidrata desde `fil-from` (YYYY-MM)
- Presets del dashboard escriben en los campos globales de fecha
- Páginas de despacho usan las fechas globales; empresa/contratista se guardan para tarjas

## Context

Hoy cada página duplica Empresa / Contratista / fechas. `url-filters.js` persiste filtros en la URL de la página actual, pero al cambiar de reporte (enlaces del menú sin query string) se pierden y `initDates()` vuelve a la semana actual.

### Architecture

Vanilla HTML/JS. Markup de la barra en `base.html`, gated por prefijo de `request.url.path`. Nuevo `global-filters.js` (localStorage + hidratación + listas empresa/contratista desde `GET /api/tarjas/general/filters`). `url-filters.js` siempre incluye los 4 IDs globales y mapea aliases de URLs antiguas (`inp-date-*`, `sel-contractor`, `sel-company`, `fil-date-*`).

IDs canónicos: `fil-from`, `fil-to`, `fil-empresa`, `fil-contratista`.

Templates usan `{% block page_filters %}` (acciones + período local como Mes) y `{% block advanced_filters %}` (Campo, CC, labor, tipo, etc.).

## Decisions

- **localStorage canónico** (`donar.globalFilters`): sobrevive navegación entre reportes. Los enlaces del menú se reescriben con Empresa / Contratista / fechas. No guardar la barra vacía antes de hidratar los selects (eso pisaba empresa/contratista). La URL gana por clave al cargar (enlaces compartidos).
- **Barra en `base.html`**: un solo markup + scripts; gating por prefijo de path (no en Chat/Sensores/Utilidades/login).
- **Listas empresa/contratista** desde `GET /api/tarjas/general/filters` (sin API nueva). Tras #165 ese endpoint ya deduplica contratistas con `unaccent`.
- **Documentos**: OC y facturación se auto-generan si empresa + contratista + fechas ya están elegidos al entrar. Notas de crédito siguen pidiendo Generar.
- **Despacho**: usa fechas globales; empresa/contratista se persisten para tarjas aunque despacho no las aplique a la query.
- **Bono mensual / calendario**: `fil-mes` / `fil-month` siguen locales; se hidratan desde `fil-from` (YYYY-MM).
- **Aliases URL**: `url-filters.js` mapea IDs legacy para no romper enlaces antiguos.
- **Modal de filtros avanzados**: los filtros específicos de página (incluido Campo) van al modal "Filtros" con badge de cantidad activa. En la barra solo quedan acciones y controles de período locales (`fil-mes` / `fil-month`).

## Implemented

- `chatai/frontend/templates/base.html` — barra `#global-filter-bar`, modal `#adv-modal`, overlay `#report-inline-loading`, carga `url-filters.js` → `global-filters.js`
- `chatai/frontend/static/global-filters.js` — localStorage, semana por defecto, populate selects, `globalFiltersReady`
- `chatai/frontend/static/url-filters.js` — merge de IDs globales + aliases + auto-consulta + overlay de loading (`runReportQuery`). Páginas nuevas: `autoTriggerFromURL(ids, queryFn)`. Notas y descarga masiva opt-out con `data-skip-auto-report`.
- `chatai/frontend/static/styles.css` — barra global, modal, overlay de loading
- 22 templates — `{% block page_filters %}` + `{% block advanced_filters %}`
- JS de reportes — leen IDs globales; `await globalFiltersReady`; `autoTriggerFromURL` dispara la consulta al entrar y al cambiar la barra
- OC / facturación — `generate()` muestra el mismo overlay; no se auto-genera si faltan empresa+contratista+fechas
- `dashboard.js` — presets escriben `fil-from`/`fil-to` y persisten
- `tarjas_bono_mensual.js` — `fil-mes` hidratado desde `fil-from`
- Páginas despacho — fechas globales; fallback semana
- Tests UI (`test_136`, `test_153`) — aserciones apuntan a `base.html` para IDs globales

## Routes

No new API routes — frontend only. Reuses `GET /api/tarjas/general/filters`.

## Tests

Manual only (browser). No automated frontend tests (same as #3).
Static UI assertions updated in `test_136_registros_campo.py` and `test_153_detalle_tractorista_pivote.py`.

## Manual QA

1. Abrir `/tarjas/general`: ver barra sticky con Empresa, Contratista, Desde, Hasta; semana actual si no hay valores guardados.
2. Elegir empresa + contratista + rango; ir a `/tarjas/detalle` **sin** pulsar Consultar — mismos valores en la barra y el reporte carga solo; Campo, CC, labor y tipo en el modal Filtros.
3. Abrir un enlace con `?fil-from=…&fil-empresa=…` — esos valores ganan sobre localStorage.
4. Dashboard: presets 7/14/Este mes/3 meses escriben fechas globales y se reflejan al ir a otro reporte.
5. `/odoo/tarjas` y `/odoo/facturacion`: si empresa + contratista + fechas ya están, el documento se genera al entrar; si faltan, esperar Generar.
6. `/tarjas/bono-mensual`: `fil-mes` ≈ YYYY-MM de `fil-from`; la consulta corre al entrar.
7. Despacho (`/despacho/guia`, etc.): usan fechas globales; empresa/contratista siguen en localStorage para tarjas.
8. Chat IA / Sensores / login: **sin** barra global.
9. Modal Filtros: el botón solo aparece si la página tiene filtros avanzados; el badge muestra cuántos están activos; Consultar del modal dispara el Consultar de la página.
