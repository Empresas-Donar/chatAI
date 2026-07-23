"""
Regression tests for issue #25: labor name with extra space after opening parenthesis
fails to match in tarjas_reporte_odoo view (l1 JOIN strategy).

Root cause: tarjas_labores stores 'CONSTRUCCIÓN INFRAESTRUCTURA (caminos, cercos, puentes)'
but tarjas_reporte has 'CONSTRUCCIÓN INFRAESTRUCTURA ( caminos, cercos, puentes)' — one
extra space after '('. The old normalization collapsed multi-spaces but not a single space
after '('. The fix extends normalization to also strip spaces adjacent to parentheses.
"""

import re


# ---------------------------------------------------------------------------
# Pure-Python replication of the SQL normalization used in the view
# ---------------------------------------------------------------------------


def _normalize_old(name: str) -> str:
    """Old normalization: collapse multiple whitespace only."""
    return re.sub(r"\s+", " ", name.lower()).strip()


def _normalize_new(name: str) -> str:
    """New normalization: collapse whitespace + strip spaces adjacent to parentheses."""
    s = re.sub(r"\s+", " ", name.lower()).strip()
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s


# ---------------------------------------------------------------------------
# Regression test — issue #25
# ---------------------------------------------------------------------------


class TestIssue25LaborConstruccionRegression:
    """test_25_labor_construccion_sin_mapeo_regression: verifies the normalization fix."""

    TABLA_NAME = "CONSTRUCCIÓN INFRAESTRUCTURA (caminos, cercos, puentes)"
    REPORTE_NAME = "CONSTRUCCIÓN INFRAESTRUCTURA ( caminos, cercos, puentes)"

    def test_25_labor_construccion_sin_mapeo_regression_old_fails(self):
        """Old normalization does NOT match — this is what caused the bug."""
        assert _normalize_old(self.TABLA_NAME) != _normalize_old(self.REPORTE_NAME), (
            "Old normalization should NOT match (this documents the bug)"
        )

    def test_25_labor_construccion_sin_mapeo_regression_new_matches(self):
        """New normalization DOES match — this is the fix."""
        assert _normalize_new(self.TABLA_NAME) == _normalize_new(self.REPORTE_NAME), (
            f"Expected match after normalization:\n"
            f"  tabla:   {_normalize_new(self.TABLA_NAME)!r}\n"
            f"  reporte: {_normalize_new(self.REPORTE_NAME)!r}"
        )

    def test_normalized_value_is_correct(self):
        """Normalized value strips extra space and preserves content."""
        result = _normalize_new(self.REPORTE_NAME)
        assert result == "construcción infraestructura (caminos, cercos, puentes)"

    def test_space_before_closing_paren(self):
        """Normalization also handles space before closing parenthesis."""
        s = "LABOR ( descripción )"
        assert _normalize_new(s) == "labor (descripción)"

    def test_no_paren_unchanged(self):
        """Names without parentheses are unaffected by the extra normalization steps."""
        name = "COSECHA DE CEREZOS"
        assert _normalize_new(name) == _normalize_old(name) == "cosecha de cerezos"

    def test_multi_space_still_collapsed(self):
        """Multiple consecutive spaces are still collapsed (existing behavior preserved)."""
        name = "PODA  DE  MANZANOS"
        assert _normalize_new(name) == "poda de manzanos"

    def test_prefix_bracket_strategy_unaffected(self):
        """Bracket-prefix names like '[2.1]AMARRA' don't regress with new normalization."""
        name = "[2.1]AMARRA"
        # These use the l2 strategy (code extraction), not l1 normalization,
        # but verify new normalization does not corrupt them.
        assert _normalize_new(name) == "[2.1]amarra"

    def test_cross_farm_isolation(self):
        """
        Normalization is stateless — same input always yields same output regardless
        of which farm's data is being processed (no shared mutable state).
        """
        talagante_labor = "CONSTRUCCIÓN INFRAESTRUCTURA ( caminos, cercos, puentes)"
        isla_labor = "CONSTRUCCIÓN INFRAESTRUCTURA (caminos, cercos, puentes)"
        # Both farms' data normalizes to the same canonical form
        assert _normalize_new(talagante_labor) == _normalize_new(isla_labor)
