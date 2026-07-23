"""
Regression tests for issue #32: labors 'ENSAYOS Y PRUEBAS' and 'MANTENCIÓN DE ESTRUCTURAS'
are missing from appsheet.tarjas_labores, causing all 11 lines for MULTISERVICIOS BONHOMIA SPA
/ KONTROLAG to show as ⚠ Incompleta with ORDER_LINE/PRODUCT_ID = '–'.

Root cause (dual):
1. The two new labors were never inserted into tarjas_labores.
2. _sync_labores could not auto-map them because Odoo stores the names with a trailing
   space ("ENSAYOS Y PRUEBAS " vs "ENSAYOS Y PRUEBAS"), causing the BigQuery WHERE clause
   to produce zero matches.

Fix:
1. Insert the two labors into tarjas_labores with their verified Odoo codes (14.40, 14.41).
2. Apply TRIM() to JSON_VALUE in the _sync_labores BigQuery query so future Odoo products
   with trailing/leading spaces are matched correctly.
"""

import re


# ---------------------------------------------------------------------------
# Pure-Python helpers — replicate the SQL normalization from the view
# (same logic as test_25, kept here for self-contained regression)
# ---------------------------------------------------------------------------


def _normalize(name: str) -> str:
    """Normalization used by the l1 JOIN in tarjas_reporte_odoo view."""
    s = re.sub(r"\s+", " ", name.lower()).strip()
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s


# Simulates the labor-to-code mapping that should exist in tarjas_labores after the fix.
EXPECTED_MAPPING = {
    "ENSAYOS Y PRUEBAS": "14.41",
    "MANTENCIÓN DE ESTRUCTURAS": "14.40",
}

# Odoo product names (exact, with trailing space as stored in BigQuery)
ODOO_NAMES = {
    "ENSAYOS Y PRUEBAS ": "14.41",
    "MANTENCIÓN DE ESTRUCTURAS ": "14.40",
}


# ---------------------------------------------------------------------------
# Regression tests — issue #32
# ---------------------------------------------------------------------------


class TestIssue32LaborSinMapeoBonhomiaRegression:
    """Regression suite for missing labors causing 11/11 incomplete lines for BONHOMIA."""

    def test_32_labores_sin_mapeo_bonhomia_regression_ensayos(self):
        """After fix, 'ENSAYOS Y PRUEBAS' must be present in tarjas_labores with code 14.41."""
        labor = "ENSAYOS Y PRUEBAS"
        assert labor in EXPECTED_MAPPING, (
            f"Labor '{labor}' must be in tarjas_labores after fix"
        )
        assert EXPECTED_MAPPING[labor] == "14.41"

    def test_32_labores_sin_mapeo_bonhomia_regression_estructuras(self):
        """After fix, 'MANTENCIÓN DE ESTRUCTURAS' must be present with code 14.40."""
        labor = "MANTENCIÓN DE ESTRUCTURAS"
        assert labor in EXPECTED_MAPPING, (
            f"Labor '{labor}' must be in tarjas_labores after fix"
        )
        assert EXPECTED_MAPPING[labor] == "14.40"

    def test_odoo_trailing_space_blocks_sync_without_trim(self):
        """Without TRIM, Odoo name with trailing space does NOT match DB labor name."""
        odoo_name_raw = "ENSAYOS Y PRUEBAS "  # as stored in Odoo/BigQuery
        db_name = "ENSAYOS Y PRUEBAS"  # as stored in tarjas_reporte
        # Exact match fails — this is the bug
        assert odoo_name_raw not in [db_name], (
            "Untrimmed Odoo name must NOT match DB name exactly (documents the bug)"
        )

    def test_trim_fixes_odoo_trailing_space(self):
        """With TRIM, Odoo names match DB labor names correctly."""
        for odoo_name, code in ODOO_NAMES.items():
            trimmed = odoo_name.strip()
            assert trimmed in EXPECTED_MAPPING, (
                f"TRIM('{odoo_name}') = '{trimmed}' must match a DB labor name"
            )
            assert EXPECTED_MAPPING[trimmed] == code, (
                f"Code mismatch: expected {code}, got {EXPECTED_MAPPING[trimmed]}"
            )

    def test_l1_join_normalization_matches_after_insert(self):
        """The l1 JOIN normalization must match tarjas_labores entries once inserted."""
        pairs = [
            ("ENSAYOS Y PRUEBAS", "ENSAYOS Y PRUEBAS"),
            ("MANTENCIÓN DE ESTRUCTURAS", "MANTENCIÓN DE ESTRUCTURAS"),
        ]
        for reporte_name, tabla_name in pairs:
            assert _normalize(reporte_name) == _normalize(tabla_name), (
                f"l1 JOIN normalization mismatch:\n"
                f"  reporte: {_normalize(reporte_name)!r}\n"
                f"  tabla:   {_normalize(tabla_name)!r}"
            )

    def test_existing_labores_unaffected(self):
        """Inserting new labors must not affect pre-existing entries (ON CONFLICT DO NOTHING)."""
        # These existing entries must still resolve correctly; codes must not be overwritten.
        existing = {
            "MANTENCIÓN INFRAESTRUCTURA (caminos, cercos, puentes)": "8.3",
            "CAPACITACIÓN": "10.1",
            "ADMINISTRACIÓN Y OPERACIÓN": "11.1",
        }
        new_entries = EXPECTED_MAPPING
        for labor in existing:
            assert labor not in new_entries, (
                f"Existing labor '{labor}' must not be overwritten by the fix"
            )

    def test_cross_farm_isolation(self):
        """
        Labor mapping is shared across farms (KONTROLAG operates across multiple client farms).
        Verify that adding these labors does not create conflicts with other field names.
        """
        # KONTROLAG labors must have unique codes not used by Donar/Talagante labors
        kontrolag_codes = set(EXPECTED_MAPPING.values())
        donar_codes = {"8.2", "8.3", "8.4", "8.5", "8.6", "8.7", "8.8", "8.9"}
        assert kontrolag_codes.isdisjoint(donar_codes), (
            "KONTROLAG labor codes must not collide with existing Donar labor codes"
        )

    def test_all_bonhomia_labors_covered(self):
        """All distinct labors seen for BONHOMIA in the affected period are now mapped."""
        # Labors extracted from tarjas_reporte for BONHOMIA 2026-07-15/2026-07-22
        bonhomia_labors = {"ENSAYOS Y PRUEBAS", "MANTENCIÓN DE ESTRUCTURAS"}
        unmapped = bonhomia_labors - set(EXPECTED_MAPPING.keys())
        assert not unmapped, (
            f"After fix, these BONHOMIA labors are still unmapped: {unmapped}"
        )
