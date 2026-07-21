"""
test_tarjas_general.py
-----------------------
Regression tests for issue #10: /tarjas/general should show only top 6 workers
in the person ranking table, not all workers.

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_tarjas_general.py -v
"""

import sys
from pathlib import Path

# Allow importing backend modules if needed
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ---------------------------------------------------------------------------
# Static analysis: verify LIMIT 6 is present in the person_ranking query
# ---------------------------------------------------------------------------


def _get_controller_source() -> str:
    path = (
        Path(__file__).parent.parent
        / "backend"
        / "controllers"
        / "tarjas_controller.py"
    )
    return path.read_text(encoding="utf-8")


class TestPersonRankingLimit:
    """Issue #10 regression — person_ranking query must use LIMIT 6."""

    def test_10_ranking_top6_regression(self):
        """Regression: the person_ranking SQL block in get_tarjas_general must contain LIMIT 6."""
        source = _get_controller_source()

        # Find the person ranking block and verify LIMIT 6 appears after it
        ranking_block_start = source.find("# 2) Person ranking")
        assert ranking_block_start != -1, (
            "Could not find '# 2) Person ranking' comment in tarjas_controller.py"
        )

        # The chart CTE block starts after; take only the ranking section
        chart_block_start = source.find("# 3) Daily average", ranking_block_start)
        assert chart_block_start != -1, (
            "Could not find '# 3) Daily average' comment in tarjas_controller.py"
        )

        ranking_section = source[ranking_block_start:chart_block_start]

        assert "LIMIT 6" in ranking_section.upper(), (
            "The person_ranking query in get_tarjas_general must contain 'LIMIT 6'. "
            "Without this, the table shows ALL workers instead of only the top 6."
        )

    def test_limit_value_is_exactly_6(self):
        """The person_ranking LIMIT must be exactly 6, not some other number."""
        source = _get_controller_source()

        ranking_start = source.find("# 2) Person ranking")
        chart_start = source.find("# 3) Daily average", ranking_start)
        ranking_section = source[ranking_start:chart_start]

        import re

        limit_matches = re.findall(r"LIMIT\s+(\d+)", ranking_section, re.IGNORECASE)
        assert limit_matches, "No LIMIT clause found in person_ranking section."
        assert all(int(n) == 6 for n in limit_matches), (
            f"Expected LIMIT 6 in person_ranking, found: {limit_matches}"
        )

    def test_chart_cte_also_limits_to_6(self):
        """The chart_data CTE (top_workers) must also use LIMIT 6 (regression guard)."""
        source = _get_controller_source()

        chart_start = source.find("# 3) Daily average by labor")
        if chart_start == -1:
            chart_start = source.find("# 3) Daily average")
        assert chart_start != -1, (
            "Could not find '# 3) Daily average' comment in tarjas_controller.py"
        )

        # Find end of function — look for the return statement after chart_data
        return_idx = source.find("return {", chart_start)
        chart_section = source[chart_start:return_idx]

        import re

        limit_matches = re.findall(r"LIMIT\s+(\d+)", chart_section, re.IGNORECASE)
        assert limit_matches, "No LIMIT clause found in chart_data (top_workers CTE)."
        assert all(int(n) == 6 for n in limit_matches), (
            f"Expected LIMIT 6 in chart CTE, found: {limit_matches}"
        )


class TestRankingHtmlTitle:
    """Issue #10 regression — HTML template must show 'Top 6' in ranking section title."""

    def _get_html_source(self) -> str:
        path = (
            Path(__file__).parent.parent
            / "frontend"
            / "templates"
            / "tarjas_general.html"
        )
        return path.read_text(encoding="utf-8")

    def test_ranking_title_includes_top6(self):
        """The ranking card title in tarjas_general.html must mention 'Top 6'."""
        html = self._get_html_source()
        # Look for the ranking card title containing "Top 6"
        assert "Top 6" in html, (
            "tarjas_general.html ranking section must include 'Top 6' in the card title."
        )

    def test_ranking_title_includes_ranking_label(self):
        """The ranking card title must still reference 'Ranking por persona'."""
        html = self._get_html_source()
        assert "Ranking por persona" in html, (
            "tarjas_general.html must still contain 'Ranking por persona' in the title."
        )
