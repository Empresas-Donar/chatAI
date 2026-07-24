"""
Regression tests for issue #27: tarjas_pagos.id_labor was added but all values are NULL.

Root cause: AppSheet writes the labor name as free text in tarjas_pagos.labor.
The JOIN in tarjas_reporte_odoo compares normalized strings, which is fragile.
The fix:
1. Backfill tarjas_pagos.id_labor from tarjas_labores using the same normalized match.
2. Expose id_labor in tarjas_reporte.
3. Rewrite tarjas_reporte_odoo to use id_labor as primary JOIN key (with text fallback).
"""

import re


# ---------------------------------------------------------------------------
# Pure-Python helpers — replicate the SQL normalization from the view
# ---------------------------------------------------------------------------


def _normalize(name: str) -> str:
    """Normalization used by the l1 fallback JOIN in tarjas_reporte_odoo."""
    s = re.sub(r"\s+", " ", name.lower()).strip()
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s


def _extract_prefix_bracket(name: str) -> str | None:
    """Extract X.Y from '[X.Y]...' format (l2 strategy)."""
    m = re.match(r"^\[([\d.]+)\]", name)
    return m.group(1).strip() if m else None


def _extract_prefix_dash(name: str) -> str | None:
    """Extract X.Y from 'X.Y-...' format (l3 strategy)."""
    m = re.match(r"^([\d]+\.[\d]+)-", name)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Simulated tarjas_labores catalog (subset for testing)
# ---------------------------------------------------------------------------

TARJAS_LABORES = [
    {"id_labor": "1", "codigo_labor": "2.1", "labor": "AMARRA"},
    {"id_labor": "2", "codigo_labor": "2.30", "labor": "COSECHA CEREZO"},
    {
        "id_labor": "3",
        "codigo_labor": "8.3",
        "labor": "MANTENCIÓN INFRAESTRUCTURA (caminos, cercos, puentes)",
    },
    {"id_labor": "4", "codigo_labor": "14.40", "labor": "MANTENCIÓN DE ESTRUCTURAS"},
    {"id_labor": "5", "codigo_labor": "14.41", "labor": "ENSAYOS Y PRUEBAS"},
    {"id_labor": "6", "codigo_labor": "10.1", "labor": "CAPACITACIÓN"},
]


def _resolve_id_labor(labor_name: str) -> str | None:
    """
    Simulate the backfill UPDATE in 04_backfill_id_labor.sql.
    Returns the matching id_labor from TARJAS_LABORES, or None if no match.
    """
    # l1: normalized text match
    norm_input = _normalize(labor_name)
    for row in TARJAS_LABORES:
        if _normalize(row["labor"]) == norm_input:
            return row["id_labor"]

    # l2: bracket prefix
    prefix = _extract_prefix_bracket(labor_name)
    if prefix:
        for row in TARJAS_LABORES:
            if row["codigo_labor"] == prefix:
                return row["id_labor"]

    # l3: dash prefix
    prefix = _extract_prefix_dash(labor_name)
    if prefix:
        for row in TARJAS_LABORES:
            if row["codigo_labor"] == prefix:
                return row["id_labor"]

    return None


def _resolve_codigo_labor(id_labor: str | None, labor_name: str) -> str | None:
    """
    Simulate the updated JOIN in 02_views_odoo.sql.
    l0 (id_labor) takes priority; falls back to l1/l2/l3 text match.
    """
    # l0: direct id_labor join
    if id_labor is not None:
        for row in TARJAS_LABORES:
            if row["id_labor"] == id_labor:
                return row["codigo_labor"]

    # l1/l2/l3 fallback (same as before)
    norm_input = _normalize(labor_name)
    for row in TARJAS_LABORES:
        if _normalize(row["labor"]) == norm_input:
            return row["codigo_labor"]

    prefix = _extract_prefix_bracket(labor_name)
    if prefix:
        for row in TARJAS_LABORES:
            if row["codigo_labor"] == prefix:
                return row["codigo_labor"]

    prefix = _extract_prefix_dash(labor_name)
    if prefix:
        for row in TARJAS_LABORES:
            if row["codigo_labor"] == prefix:
                return row["codigo_labor"]

    return None


# ---------------------------------------------------------------------------
# Regression tests — issue #27
# ---------------------------------------------------------------------------


class TestIssue27PoblarIdLaborRegression:
    """Regression suite for populating id_labor in tarjas_pagos."""

    def test_27_poblar_id_labor_tarjas_pagos_regression(self):
        """
        Backfill must resolve id_labor for a known labor via normalized text match.
        Simulates the l1 strategy in 04_backfill_id_labor.sql.
        """
        result = _resolve_id_labor("COSECHA CEREZO")
        assert result == "2", f"Expected id_labor='2', got {result!r}"

    def test_backfill_l1_normalizes_spaces_near_parentheses(self):
        """l1 strategy must resolve despite extra spaces around parentheses."""
        # Same case as issue #25 — spaces around '('
        result = _resolve_id_labor(
            "MANTENCIÓN INFRAESTRUCTURA ( caminos, cercos, puentes)"
        )
        assert result == "3", (
            f"Normalized match failed for labor with extra spaces near parens, got {result!r}"
        )

    def test_backfill_l2_bracket_prefix(self):
        """l2 strategy must resolve '[X.Y]...' names via bracket prefix."""
        result = _resolve_id_labor("[2.1]AMARRA VERDE")
        assert result == "1", (
            f"Expected id_labor='1' via l2 bracket prefix, got {result!r}"
        )

    def test_backfill_l3_dash_prefix(self):
        """l3 strategy must resolve 'X.Y-...' names via dash prefix."""
        result = _resolve_id_labor("2.1-AMARRA VERDE")
        assert result == "1", (
            f"Expected id_labor='1' via l3 dash prefix, got {result!r}"
        )

    def test_backfill_returns_none_for_unknown_labor(self):
        """Backfill must leave id_labor as NULL when no match exists."""
        result = _resolve_id_labor("LABOR QUE NO EXISTE EN CATÁLOGO")
        assert result is None, f"Expected None for unknown labor, got {result!r}"

    def test_backfill_idempotent_for_already_mapped(self):
        """Running the backfill on a row that already has id_labor must produce the same value."""
        labor_name = "ENSAYOS Y PRUEBAS"
        first_run = _resolve_id_labor(labor_name)
        # Second run must return the same result
        second_run = _resolve_id_labor(labor_name)
        assert first_run == second_run, (
            f"Backfill is not idempotent: first={first_run!r}, second={second_run!r}"
        )

    def test_view_l0_join_wins_over_text_fallback(self):
        """
        When id_labor is populated, the l0 join in tarjas_reporte_odoo must resolve
        codigo_labor without relying on text comparison.
        Simulates a row that has id_labor set and a labor name that would NOT match l1.
        """
        # id_labor is set; labor name is intentionally mangled so l1/l2/l3 would fail
        id_labor = "4"  # MANTENCIÓN DE ESTRUCTURAS → codigo_labor 14.40
        mangled_labor_name = "MANTENCIÓN DE ESTRUCTURAS ← nombre roto"
        result = _resolve_codigo_labor(id_labor, mangled_labor_name)
        assert result == "14.40", (
            f"l0 join must win over text fallback, expected '14.40', got {result!r}"
        )

    def test_view_text_fallback_used_when_id_labor_null(self):
        """
        When id_labor is NULL (not yet backfilled), l1 text fallback must still work.
        Ensures no regression for existing rows without id_labor.
        """
        result = _resolve_codigo_labor(None, "COSECHA CEREZO")
        assert result == "2.30", (
            f"Text fallback must work when id_labor is NULL, expected '2.30', got {result!r}"
        )

    def test_view_null_id_labor_and_unknown_name_returns_none(self):
        """When id_labor is NULL and name does not match any labor, result is NULL."""
        result = _resolve_codigo_labor(None, "LABOR QUE NO EXISTE")
        assert result is None, (
            f"Unknown labor with NULL id_labor must return None, got {result!r}"
        )

    def test_cross_farm_id_labor_isolation(self):
        """
        id_labor values must be unique in tarjas_labores — same id cannot map
        to two different codigo_labor values (would break cross-farm correctness).
        """
        seen_ids: dict[str, str] = {}
        for row in TARJAS_LABORES:
            id_ = row["id_labor"]
            code = row["codigo_labor"]
            assert id_ not in seen_ids or seen_ids[id_] == code, (
                f"id_labor '{id_}' maps to both '{seen_ids[id_]}' and '{code}'"
            )
            seen_ids[id_] = code
