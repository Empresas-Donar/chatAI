# Spec: sync_cc drops new CCs whose code collides with another company

**Issue:** #5
**Branch:** `5-sync-cc-duplicate-codes`

## What

`apps/sync_cc.py` silently discards active Odoo CCs whose `code` value is already held by a
different CC from another company. Because `fetch_odoo_cc` builds `by_code` with bare `code`
as the key (first-seen-wins), the older company-6 CCs (IDs 255, 284, 285, 297, 299) occupy
codes 616, 619, 620, 629, 630 before the newer PIMENTONES 26-27 CCs (company-2, IDs 733–749)
are processed. Those newer CCs are never inserted into `appsheet.tarjas_cc`.

## Acceptance Criteria

- All active CCs from BigQuery are inserted into `appsheet.tarjas_cc`, regardless of whether
  another CC from a different company shares the same code.
- When two active CCs share the same `code`, the one from a lower `company_id` (or lower `id`)
  keeps `id_cc = code`; the other gets `id_cc = "<code>-c<company_id>"` to remain unique.
- No existing `tarjas_cc` rows are deleted or altered by the fix.
- Running sync twice produces the same result (idempotent via `ON CONFLICT DO NOTHING`).
- Regression test: two CCs with the same code but different `company_id` both appear after sync.

## Context

- **File:** `apps/sync_cc.py` — the only script that reads `CC_analiticos` from BigQuery and
  writes to `appsheet.tarjas_cc`.
- **Root cause line:** `fetch_odoo_cc`, inside the active-CC loop:
  ```python
  if code and code not in by_code:
      by_code[code] = {...}   # second CC with same code is silently dropped
  ```
- **Colliding codes discovered in BigQuery:**

  | Code | Company-6 CC (older, wins) | Company-2 CC (PIMENTONES, dropped) |
  |------|---------------------------|-------------------------------------|
  | 616  | ID 297 CARRO DE ARRASTRE NEGRO | ID 733 MT PIM.ROJO TEMP 26-27 |
  | 619  | ID 299 GRUA HORQUILLA CLARK    | ID 736 AL1 PIM.ROJO TEMP 26-27 |
  | 620  | ID 285 SERVICIO COSECHA        | ID 737 AL2 PIM.AMARILLO TEMP 26-27 |
  | 629  | ID 255 LOGISTICA               | ID 747 PM PIM MORADO TEMP 26-27 |
  | 630  | ID 284 Gastos Operadores.      | ID 748 PM PIM NARANJO TEMP 26-27 |

- `COMPANY_TO_CAMPO = {1: 1, 2: 1, 3: 2, 5: 3, 6: 4, 7: 4}` — company 2 → campo 1 (Isla de Maipo).

## Decisions

- Use `(code, company_id)` as composite key inside `fetch_odoo_cc` to collect **all** active CCs.
- Determine `id_cc` in a second pass: sort candidates per code by `(company_id, id)` ascending;
  the first (canonical) keeps bare `code`; subsequent ones get `<code>-c<company_id>`.
  This is stable and deterministic — same BigQuery data always yields the same `id_cc`.
- The `valor_odoo` JSON key is the Odoo numeric `id` (unchanged); only `id_cc` (the PK column
  in `tarjas_cc`) is affected.
- No schema change to `appsheet.tarjas_cc` is needed.
- `despacho_cc` sync is unaffected — it looks up by `code` via product name prefix, not `id_cc`.

## Implemented

- `apps/sync_cc.py` — replaced bare `code`-keyed `by_code` dict with `(code, company_id)` composite
  collection, then resolves unique `id_cc` per code in a second pass (lowest company_id wins bare code,
  others get `<code>-c<company_id>` suffix). Added `from collections import defaultdict` import.
- `chatai/tests/test_sync_cc.py` — new test file: 6 unit tests covering the regression, unique-code
  pass-through, null-code exclusion, three-company collision, archived exclusion, and cross-farm isolation.

## Tests

6 passed, 0 failed · isolation: ✅ (test_cross_farm_isolation validates company-2 / company-3 separation)

## Manual QA

1. Run `python apps/sync_cc.py` against the real DB and check the log for
   `insertados:` — the count should include the PIMENTONES 26-27 CCs (at minimum 17 new rows
   if previously absent).
2. Query `SELECT id_cc, cultivo, valor_odoo FROM appsheet.tarjas_cc WHERE id_cc IN ('616','619','620','629','630','616-c2','619-c2','620-c2','629-c2','630-c2')` —
   both the company-6 row (bare code) and the company-2 row (`-c2` suffix) must be present.
3. In AppSheet, open the Tarjas app and verify that the new PIMENTONES 26-27 cuarteles appear
   in the CC picker for labor assignment.
