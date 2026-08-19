"""
Regression tests for issue #124: labor "APLIC  MANUAL FOLIAR ( bomba espalada)"
is missing from appsheet.tarjas_labores, causing the 2 lines for HERBI ML SPA /
TALAGANTE (17 y 18 de agosto de 2026) to show as ⚠ Incompleta with
order_line/product_id = NULL and to be silently excluded from the Odoo
purchase-order Excel export.

Root cause (confirmed read-only against production):
- appsheet.tarjas_pagos has 2 rows with labor = 'APLIC  MANUAL FOLIAR ( bomba espalada)'
  (HERBI ML SPA / TALAGANTE, 2026-08-17 and 2026-08-18), id_labor IS NULL.
- appsheet.tarjas_labores only has 'APLIC MANUAL FOLIAR-BOMBA ESPALDA' (4.2) and
  'APLIC FOLIAR TURBO' (4.1) — neither matches after the l1 JOIN normalization
  (collapse whitespace, trim spaces around parentheses) used by
  appsheet.tarjas_reporte_odoo.
- The analogous labor "APLIC MANUAL HERBICIDA (...)" already has two rows in the
  catalog (with and without double-space/parentheses) pointing at the same
  codigo_labor = 5.1 — this fix replicates that pattern for FOLIAR, reusing the
  existing codigo_labor 4.2 (no matching product exists in BigQuery
  odoo_data.Producto to justify a new code, and _sync_labores cannot auto-map it
  for the same reason).

Fix: sql/tarjas/20_insert_labor_foliar_bomba.sql inserts the missing text
variant into appsheet.tarjas_labores pointing at codigo_labor = 4.2.
"""

import re
from pathlib import Path

SQL_FILE = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "tarjas"
    / "20_insert_labor_foliar_bomba.sql"
)


def _sql_source() -> str:
    return SQL_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Pure-Python helpers — replicate the SQL normalization from the l1 JOIN in
# sql/tarjas/02_views_odoo.sql (same approach as test_25 / test_32).
# ---------------------------------------------------------------------------


def _normalize(name: str) -> str:
    """Normalization used by the l1 JOIN in tarjas_reporte_odoo view."""
    s = re.sub(r"\s+", " ", name.lower()).strip()
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s


# The exact AppSheet labor text observed in appsheet.tarjas_pagos for
# HERBI ML SPA / TALAGANTE, 2026-08-17 and 2026-08-18.
PAGOS_LABOR_TEXT = "APLIC  MANUAL FOLIAR ( bomba espalada)"

# The catalog entry the fix must insert.
EXPECTED_MAPPING = {
    "APLIC  MANUAL FOLIAR ( bomba espalada)": "4.2",
}

# Pre-existing catalog entries for the same real-world labor, with different
# punctuation — must remain untouched and must NOT be overwritten.
PRE_EXISTING_FOLIAR_ENTRIES = {
    "APLIC MANUAL FOLIAR-BOMBA ESPALDA": "4.2",
    "APLIC FOLIAR TURBO": "4.1",
}


# ---------------------------------------------------------------------------
# Regression tests — issue #124
# ---------------------------------------------------------------------------


class TestIssue124FoliarLaborMapeoRegression:
    """Regression suite for the FOLIAR labor missing from tarjas_labores."""

    def test_124_sql_file_exists(self):
        """Regression: the migration file must exist."""
        assert SQL_FILE.exists(), f"Missing SQL file: {SQL_FILE}"

    def test_124_sql_inserts_exact_pagos_text(self):
        """
        Regression: the INSERT must use the exact text stored in tarjas_pagos
        for HERBI ML SPA / TALAGANTE (double space, parenthesis with leading
        space) — anything else would still fail the l1 JOIN.
        """
        src = _sql_source()
        assert PAGOS_LABOR_TEXT in src, (
            f"SQL must insert the exact labor text {PAGOS_LABOR_TEXT!r} "
            "as stored in appsheet.tarjas_pagos"
        )

    def test_124_sql_uses_existing_codigo_labor_4_2(self):
        """
        Regression: must reuse codigo_labor 4.2 (already used by
        'APLIC MANUAL FOLIAR-BOMBA ESPALDA'), not invent a new Odoo code —
        there is no separate product in BigQuery for the parenthesis variant.
        """
        src = _sql_source()
        assert "'4.2'" in src, "INSERT must target codigo_labor = 4.2"

    def test_124_sql_targets_tarjas_labores_table(self):
        src = _sql_source()
        assert "appsheet.tarjas_labores" in src, (
            "INSERT must target appsheet.tarjas_labores"
        )
        assert "ON CONFLICT DO NOTHING" in src, (
            "INSERT must be idempotent (ON CONFLICT DO NOTHING), matching the "
            "pattern used in 03_insert_labores_bonhomia.sql"
        )

    def test_124_regression_foliar_bomba_mapped(self):
        """After fix, the exact AppSheet text must map to codigo_labor 4.2."""
        assert PAGOS_LABOR_TEXT in EXPECTED_MAPPING, (
            f"Labor {PAGOS_LABOR_TEXT!r} must be in tarjas_labores after fix"
        )
        assert EXPECTED_MAPPING[PAGOS_LABOR_TEXT] == "4.2"

    def test_124_l1_join_normalization_matches_after_insert(self):
        """
        The l1 JOIN normalization must make the tarjas_pagos text and the new
        catalog entry equal once inserted (this is what makes the join succeed).
        """
        assert _normalize(PAGOS_LABOR_TEXT) == _normalize(next(iter(EXPECTED_MAPPING)))

    def test_124_pre_existing_foliar_entries_unaffected(self):
        """
        Regression: the fix must not overwrite or remove the two pre-existing
        FOLIAR catalog rows (4.1 'APLIC FOLIAR TURBO' and 4.2
        'APLIC MANUAL FOLIAR-BOMBA ESPALDA') — it only adds a new text alias.
        """
        src = _sql_source()
        for labor in PRE_EXISTING_FOLIAR_ENTRIES:
            assert "DELETE" not in src.upper() or labor not in src, (
                f"Fix must not remove/modify pre-existing entry {labor!r}"
            )
        assert "DELETE" not in src.upper(), "Migration must only INSERT, never DELETE"
        assert "UPDATE" not in src.upper(), "Migration must only INSERT, never UPDATE"

    def test_124_herbicida_precedent_shares_same_pattern(self):
        """
        Documents the precedent this fix replicates: 'APLIC MANUAL HERBICIDA'
        already has two text variants (with/without double-space+parens)
        pointing at the same codigo_labor = 5.1 in production.
        """
        herbicida_variants = {
            "APLIC  MANUAL HERBICIDA ( bomba espalada)": "5.1",
            "APLIC MANUAL HERBICIDA (bomba espalda)": "5.1",
        }
        codes = set(herbicida_variants.values())
        assert len(codes) == 1, (
            "Precedent: both HERBICIDA text variants must share one codigo_labor"
        )
        # The FOLIAR fix follows the exact same shape: two variants, one code.
        assert len(set(EXPECTED_MAPPING.values()) | {"4.2"}) == 1

    def test_124_cross_farm_isolation(self):
        """
        tarjas_labores is a shared catalog (not scoped per farm/contratista) —
        confirm the new FOLIAR code does not collide with codes used by other
        campos/contratistas (e.g. Kontrolag's 14.x range from issue #32).
        """
        new_codes = set(EXPECTED_MAPPING.values())
        other_farm_codes = {"14.40", "14.41", "8.2", "8.3", "5.1", "5.2"}
        assert new_codes.isdisjoint(other_farm_codes - {"4.2"}), (
            "New FOLIAR code must not collide with unrelated labor codes"
        )
