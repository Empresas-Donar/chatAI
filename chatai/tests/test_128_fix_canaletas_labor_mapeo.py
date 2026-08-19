"""
Regression tests for issue #128: labor "CANALETAS AGUAS LLUVIA" is missing
from appsheet.tarjas_labores, causing 7 rows for HERBI ML SPA / KONTROLAG
(11 y 12 de agosto de 2026) to show as ⚠ Incompleta with
order_line/product_id = NULL and to be silently excluded from the Odoo
purchase-order Excel export.

Root cause (confirmed read-only against production + BigQuery):
- appsheet.tarjas_pagos has 7 rows with labor = 'CANALETAS AGUAS LLUVIA'
  (HERBI ML SPA / KONTROLAG, 2026-08-11 and 2026-08-12), id_labor IS NULL.
- appsheet.tarjas_labores has no row for this labor at all (not a punctuation
  variant of an existing entry, unlike issue #124 — genuinely unmapped).
- BigQuery odoo_data.Producto has the exact matching product:
  "CANALETAS AGUAS LLUVIA" -> default_code = 14.42.
- _sync_labores (the auto-map-from-BigQuery step) only runs when someone
  generates the export/preview for that exact contratista+empresa+date range;
  nobody had generated it before this was reported, so it never fired.

Fix: sql/tarjas/21_insert_labor_canaletas.sql inserts the missing labor into
appsheet.tarjas_labores pointing at codigo_labor = 14.42.
"""

from pathlib import Path

SQL_FILE = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "tarjas"
    / "21_insert_labor_canaletas.sql"
)

PAGOS_LABOR_TEXT = "CANALETAS AGUAS LLUVIA"
EXPECTED_CODIGO_LABOR = "14.42"


def _sql_source() -> str:
    return SQL_FILE.read_text(encoding="utf-8")


class TestIssue128CanaletasLaborMapeoRegression:
    """Regression suite for the CANALETAS AGUAS LLUVIA labor missing from tarjas_labores."""

    def test_128_sql_file_exists(self):
        assert SQL_FILE.exists(), f"Missing SQL file: {SQL_FILE}"

    def test_128_sql_inserts_exact_pagos_text(self):
        """
        Regression: the INSERT must use the exact text stored in tarjas_pagos
        for HERBI ML SPA / KONTROLAG — the l1 JOIN in tarjas_reporte_odoo only
        normalizes whitespace/parentheses, not arbitrary text differences.
        """
        src = _sql_source()
        assert PAGOS_LABOR_TEXT in src, (
            f"SQL must insert the exact labor text {PAGOS_LABOR_TEXT!r} "
            "as stored in appsheet.tarjas_pagos"
        )

    def test_128_sql_uses_bigquery_matched_codigo_labor(self):
        """
        Regression: must use codigo_labor 14.42, the exact match found in
        BigQuery odoo_data.Producto for this labor name.
        """
        src = _sql_source()
        assert f"'{EXPECTED_CODIGO_LABOR}'" in src, (
            f"INSERT must target codigo_labor = {EXPECTED_CODIGO_LABOR}"
        )

    def test_128_sql_targets_tarjas_labores_table(self):
        src = _sql_source()
        assert "appsheet.tarjas_labores" in src, (
            "INSERT must target appsheet.tarjas_labores"
        )
        assert "ON CONFLICT DO NOTHING" in src, (
            "INSERT must be idempotent (ON CONFLICT DO NOTHING), matching the "
            "pattern used in 03_insert_labores_bonhomia.sql and issue #124"
        )

    def test_128_sql_only_inserts_never_mutates(self):
        src = _sql_source()
        assert "DELETE" not in src.upper(), "Migration must only INSERT, never DELETE"
        assert "UPDATE" not in src.upper(), "Migration must only INSERT, never UPDATE"

    def test_128_cross_farm_isolation(self):
        """
        tarjas_labores is a shared catalog (not scoped per farm/contratista) —
        confirm the new code does not collide with codes used by other
        campos/contratistas (e.g. Kontrolag's other 14.x codes, or FOLIAR's 4.x
        from issue #124).
        """
        other_known_codes = {"14.40", "14.41", "4.1", "4.2", "8.2", "8.3", "5.1"}
        assert EXPECTED_CODIGO_LABOR not in other_known_codes, (
            "New CANALETAS code must not collide with unrelated labor codes"
        )
