# Spec: Persist report filters in URL query params

**Issue:** #3
**Branch:** `3-url-filter-params`

## What

When a user clicks "Consultar" (or the equivalent generate button) on any of the 15 report pages, all active filter values are written to the page URL as query parameters. When the page is opened with those parameters present (e.g. from a shared link), the inputs are pre-filled and the query is auto-triggered. Browser back/forward restores state.

## Acceptance Criteria

- After clicking Consultar, the browser URL updates to include all active filter values as query params (no page reload)
- Empty/unset filters are omitted from the URL
- Opening a URL with filter params pre-fills all matching inputs and auto-runs the query
- Browser back/forward navigation restores filter state and re-runs the query
- All 15 report pages covered

## Context

### Architecture

A single shared utility `chatai/frontend/static/url-filters.js` is loaded by all 15 pages. It exports two functions:

- `syncFiltersToURL(ids)` — reads the current value of each listed element id, builds URLSearchParams skipping empty values, and calls `history.pushState`
- `loadFiltersFromURL(ids, trigger)` — reads `window.location.search`, sets element values where params exist, and if any param was found calls `trigger()` instead of the default init query

Each page calls these two functions. Pages with dynamically-loaded selects (whose options come from an API) call `loadFiltersFromURL` after the API returns options so that the restored value finds its `<option>` already in the DOM.

### Pages and their filter element IDs

| Page JS | Filter input IDs |
|---|---|
| tarjas_detail | fil-from, fil-to, fil-contratista, fil-empresa, fil-cc, fil-labor, fil-campo, fil-tipo |
| tarjas_general | fil-from, fil-to, fil-cc, fil-tipo, fil-labor, fil-contratista, fil-empresa |
| tarjas_general_tractorista | fil-from, fil-to, fil-cc, fil-labor, fil-maquina, fil-contratista, fil-empresa |
| tarjas_detalle_tractorista | fil-from, fil-to, fil-contratista, fil-empresa, fil-cc, fil-labor, fil-campo |
| tarjas_contractor | fil-from, fil-to, fil-contratista, fil-empresa, fil-cc, fil-tipo, fil-labor |
| tarjas_resumen_persona | fil-from, fil-to, fil-trabajador, fil-contratista, fil-tipo, fil-empresa |
| tarjas_resumen_persona_tractorista | fil-from, fil-to, fil-trabajador, fil-tipo, fil-contratista, fil-empresa, fil-maquina |
| tarjas_resumen_horas | fil-from, fil-to, fil-trabajador, fil-tipo, fil-contratista, fil-empresa |
| despacho_resumen | fil-from, fil-to, fil-cliente |
| despacho_guia | fil-from, fil-to, fil-cliente |
| despacho_notas | fil-from, fil-to, fil-contratista, fil-campo |
| despacho_ordenes | fil-cliente, fil-producto |
| purchase_orders | inp-date-from, inp-date-to, sel-contractor, sel-company |
| billing_order | inp-date-from, inp-date-to, sel-contractor, sel-company |
| reportes | fil-from, fil-to, fil-empresa, fil-contratista |

### Special cases

- `tarjas_general_tractorista` and `tarjas_resumen_persona_tractorista`: `fil-maquina` is conditionally shown if the API returns machines — restore its value only if the element exists in DOM
- `despacho_notas`: no `loadFilters` auto-triggers queryData; button is required (generate nota). On page load with params, pre-fill but do NOT auto-trigger (document generation requires deliberate user action)
- `purchase_orders` and `billing_order`: same rationale — these generate documents. Pre-fill selects but do NOT auto-trigger
- `despacho_ordenes`: no date inputs; `fetchOrdenes` is called on DOMContentLoaded automatically, so restoring params before that is sufficient
- `reportes`: does not auto-trigger a query on load (download is manual). Pre-fill only
- `despacho_resumen`: auto-triggers via `DOMContentLoaded → fetchDashboard`. The `fil-cliente` select is populated dynamically; restore its value after `loadFilters()` resolves

## Decisions

- Shared utility file approach rather than duplicating logic in 15 files — keeps changes auditable and consistent
- `history.pushState` (not `replaceState`) so each Consultar click creates a back-forward entry
- `window.addEventListener('popstate', ...)` restores state on browser navigation
- For pages that auto-trigger on load, the URL params take precedence: if params exist, skip `initDates()` default and use param values instead
- Pages with mandatory user-selection (notas, purchase_orders, billing_order) pre-fill but do NOT auto-trigger — triggering would generate documents/PDFs silently
- The `reportes` page pre-fills checkboxes would require parsing a `reports` comma list — out of scope; only date and empresa/contratista are restored

## Implemented

- `chatai/frontend/static/url-filters.js` — new shared utility (syncFiltersToURL, loadFiltersFromURL)
- `chatai/frontend/static/tarjas_detail.js` — modified: add URL sync on Consultar, restore on load/popstate
- `chatai/frontend/static/tarjas_general.js` — same
- `chatai/frontend/static/tarjas_general_tractorista.js` — same
- `chatai/frontend/static/tarjas_detalle_tractorista.js` — same
- `chatai/frontend/static/tarjas_contractor.js` — same
- `chatai/frontend/static/tarjas_resumen_persona.js` — same
- `chatai/frontend/static/tarjas_resumen_persona_tractorista.js` — same
- `chatai/frontend/static/tarjas_resumen_horas.js` — same
- `chatai/frontend/static/despacho_resumen.js` — same
- `chatai/frontend/static/despacho_guia.js` — same
- `chatai/frontend/static/despacho_notas.js` — pre-fill only (no auto-trigger)
- `chatai/frontend/static/despacho_ordenes.js` — same (no dates)
- `chatai/frontend/static/purchase_orders.js` — pre-fill only (no auto-trigger)
- `chatai/frontend/static/billing_order.js` — pre-fill only (no auto-trigger)
- `chatai/frontend/static/reportes.js` — pre-fill dates and empresa/contratista

## Routes

No new API routes — pure frontend change.

## Tests

Manual only (browser testing). No automated tests needed for this feature since it is entirely URL/DOM manipulation with no backend logic.

## Manual QA

1. Open any report page (e.g. `/tarjas/detalle`). Select a contratista and a date range. Click Consultar. Verify the URL bar now shows `?fil-from=2025-07-14&fil-to=2025-07-20&fil-contratista=...`
2. Copy the URL from step 1 and open it in a new tab. Verify the filters are pre-filled and the query auto-runs, showing the same data.
3. On a page that just ran a query, use the browser Back button. Verify the previous URL (no params or different params) is restored and the query re-runs with those filters.
4. Open `/purchase-orders` with params `?inp-date-from=2025-07-01&inp-date-to=2025-07-07&sel-contractor=ContratistaNombre`. Verify the inputs are pre-filled but NO document is generated automatically (user must still click "Generar orden").
5. Open `/despacho/ordenes` with `?fil-cliente=Cliente+X`. Verify the cliente select is pre-filled when the query auto-runs on DOMContentLoaded.
