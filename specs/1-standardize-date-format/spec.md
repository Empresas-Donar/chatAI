# Spec: Standardize date format to DD/MM/YYYY across the platform

**Issue:** #1
**Branch:** `1-standardize-date-format`
**Labels:** bug

---

## What

User-facing dates are displayed inconsistently across the platform. Some views show `DD-MM-YYYY` (hyphen), others show `DD ene YYYY` (abbreviated month), and `despacho_ordenes` even re-formats from a raw `MM/DD/YYYY` source to `DD-MM-YYYY`. Chilean agricultural operators expect `DD/MM/YYYY` everywhere.

Internal API inputs (query params) and database storage remain ISO 8601 (`YYYY-MM-DD`). Only user-visible output changes.

---

## Acceptance Criteria

- [ ] Ninguna fecha visible en la UI se muestra en formato YYYY-MM-DD o MM/DD/YYYY
- [ ] Todas las columnas de fecha en tablas muestran DD/MM/YYYY
- [ ] Los PDFs y Excel exportados desde la plataforma muestran fechas en DD/MM/YYYY
- [ ] Existe un test de regresión o visual que verifica el formato correcto en al menos una vista clave

---

## Context

Files involved:

**Frontend JS (display formatting):**
- `chatai/frontend/static/despacho_ordenes.js` — `parseFecha()` outputs `DD-MM-YYYY` (hyphen)
- `chatai/frontend/static/despacho_resumen.js` — `fmtDate` outputs `DD-MM-YYYY` (hyphen)
- `chatai/frontend/static/despacho_guia.js` — `fmtDate` outputs `DD-MM-YYYY` (hyphen)
- `chatai/frontend/static/purchase_orders.js` — `fmtDate` outputs `DD-MM-YYYY` (hyphen)
- `chatai/frontend/static/tarjas_contractor.js` — `formatShortDate()` outputs "1 ene. 2025" via `toLocaleDateString`
- `chatai/frontend/static/tarjas_resumen_persona.js` — same `formatShortDate` pattern
- `chatai/frontend/static/tarjas_resumen_persona_tractorista.js` — same `formatShortDate` pattern
- `chatai/frontend/static/tarjas_resumen_horas.js` — same `formatShortDate` pattern
- `chatai/frontend/static/billing_order.js` — two `toLocaleDateString` calls with different formats

**Backend Python (PDF / Excel exports):**
- `chatai/backend/controllers/reports_controller.py` — `_fmt_date_display()` outputs "5 ene 2025" in PDF headers; raw `fecha` column (YYYY-MM-DD) rendered into HTML table for PDF
- `chatai/backend/controllers/tarjas_controller.py` — Excel date column headers use `"%-d %b %Y"` (e.g., "5 ene 2025")

**Already correct:**
- `chatai/frontend/static/dashboard.js` — `fmtDateFull` already outputs `DD/MM/YYYY`; `fmtDate` outputs `DD/MM` (short axis label — intentional)
- `chatai/backend/controllers/roles_controller.py` — SQL uses `TO_CHAR(..., 'DD/MM/YYYY HH24:MI')` — already correct
- `chatai/backend/controllers/looker_controller.py` — same SQL pattern — already correct
- `chatai/backend/controllers/chat_controller.py` — `.strftime("%d/%m/%Y %H:%M")` — already correct

---

## Decisions

- `formatShortDate` functions in tarjas JS files: replaced with a `fmtDate(isoStr)` helper that zero-pads and returns `DD/MM/YYYY`. The month-name style was used for display labels in the date range picker and print headers — switching to numeric keeps it consistent.
- PDF header in `reports_controller.py`: `_fmt_date_display()` kept but changed to return `DD/MM/YYYY` instead of "5 ene 2025". This is cleaner and consistent.
- Excel column date headers in `tarjas_controller.py`: changed from `"%-d %b %Y"` to `"%d/%m/%Y"`.
- `billing_order.js` short date format (day + month only): kept as `DD/MM` (no year) for the inline display; the long format changed to `DD/MM/YYYY`.
- `despacho_ordenes.js` `parseFecha()`: source data is `MM/DD/YYYY HH:MM:SS` from BigQuery — correct extraction and output changed to `DD/MM/YYYY`.
- `lang="es-CL"` on `<input type="date">` elements: `base.html` already sets `<html lang="es">` at the document level, but Chrome determines the date picker display format from the browser's UI language setting, not from the HTML `lang` attribute. Adding `lang="es-CL"` directly on each `<input type="date">` element is the mechanism Chrome actually respects for overriding the date picker format to DD/MM/YYYY — regardless of the user's browser language preference.

---

## Implemented

- `chatai/frontend/static/despacho_ordenes.js` — `parseFecha()` now outputs `DD/MM/YYYY`
- `chatai/frontend/static/despacho_resumen.js` — `fmtDate` now outputs `DD/MM/YYYY`
- `chatai/frontend/static/despacho_guia.js` — `fmtDate` now outputs `DD/MM/YYYY`
- `chatai/frontend/static/purchase_orders.js` — `fmtDate` now outputs `DD/MM/YYYY`
- `chatai/frontend/static/tarjas_contractor.js` — `formatShortDate` replaced with `fmtDate` returning `DD/MM/YYYY`
- `chatai/frontend/static/tarjas_resumen_persona.js` — same replacement
- `chatai/frontend/static/tarjas_resumen_persona_tractorista.js` — same replacement
- `chatai/frontend/static/tarjas_resumen_horas.js` — same replacement
- `chatai/frontend/static/billing_order.js` — long format changed to `DD/MM/YYYY`; short format to `DD/MM`
- `chatai/backend/controllers/reports_controller.py` — `_fmt_date_display()` now returns `DD/MM/YYYY`; raw `fecha` cells in PDF table now formatted
- `chatai/backend/controllers/tarjas_controller.py` — Excel date column headers changed to `DD/MM/YYYY`
- `chatai/frontend/templates/billing_order.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/dashboard.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/despacho_guia.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/despacho_notas.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/despacho_resumen.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/purchase_orders.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/reportes.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/tarjas_contractor.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/tarjas_detail.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/tarjas_detalle_tractorista.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/tarjas_general.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/tarjas_general_tractorista.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/tarjas_resumen_horas.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/tarjas_resumen_persona.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/frontend/templates/tarjas_resumen_persona_tractorista.html` — `lang="es-CL"` added to all `<input type="date">` elements
- `chatai/tests/test_date_format.py` — new regression tests

---

## Tests

17 passed, 0 failed · isolation: N/A (pure formatting logic, no DB queries)

Test file: `chatai/tests/test_date_format.py`
- `TestFmtDateDisplay` (7 tests) — verifies `_fmt_date_display()` from `reports_controller.py` produces DD/MM/YYYY
- `TestJsDateFunctions` (8 tests) — Python equivalents of all JS date formatting functions; verifies DD/MM/YYYY output and absence of hyphens and abbreviated month names
- `TestTarjasControllerDateFormat` (2 tests) — verifies Python `strftime` patterns used in Excel/HTML pivot headers produce DD/MM/YYYY and DD/MM respectively

---

## Manual QA

1. Navigate to `/despacho/ordenes` — click "Consultar". Verify the "Fecha" column shows dates in `DD/MM/YYYY` format (e.g., `21/07/2026`), not `21-07-2026` or `07/21/2026`.
2. Navigate to `/reportes` — select any report with a date range and download the PDF. Open it and verify the "Desde" and "Hasta" chips show dates like `21/07/2026`.
3. Navigate to `/tarjas/resumen-persona` — enter a date range and click "Consultar". Verify date column headers in the table and the downloaded Excel file show `DD/MM/YYYY`.
4. Navigate to any page with a date picker, e.g. Tarjas (`/tarjas/general`). Click on any `<input type="date">` field. Verify the date picker renders in DD/MM/YYYY format (e.g., the placeholder reads `dd/mm/aaaa` and the calendar shows day first), not in MM/DD/YYYY (US format). This must hold even if the browser's UI language is set to English (US).
