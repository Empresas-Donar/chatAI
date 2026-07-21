"""
tests/test_sync_cc.py
---------------------
Regression tests for apps/sync_cc.py — specifically the id_cc deduplication logic
that resolves colliding codes across different companies.

No BigQuery or PostgreSQL connection is required; all tests are pure-unit against
the in-process functions via direct import.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# Make the apps/ directory importable without installing the package.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps"))


def _make_rows(specs: list[dict]) -> list[dict]:
    """Build mock BigQuery row objects from dicts (subscript-accessible like real BQ rows)."""
    return list(specs)


def _run_fetch_odoo_cc(rows: list[dict]):
    """
    Import fetch_odoo_cc and call it with a mock BQ client that returns `rows`.
    Returns (by_code, archived_to_replacements).
    """
    # Patch heavy imports so we don't need real credentials on import.
    mock_bq_module = MagicMock()
    mock_sa_module = MagicMock()
    with (
        patch.dict(
            "sys.modules",
            {
                "google": MagicMock(),
                "google.cloud": MagicMock(),
                "google.cloud.bigquery": mock_bq_module,
                "google.oauth2": MagicMock(),
                "google.oauth2.service_account": mock_sa_module,
                "psycopg2": MagicMock(),
                "dotenv": MagicMock(),
            },
        ),
        patch("builtins.open", MagicMock()),
    ):
        import importlib
        import sync_cc

        importlib.reload(sync_cc)  # ensure fresh module after patching

        mock_client = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.result.return_value = iter(rows)
        mock_client.query.return_value = mock_query_result

        return sync_cc.fetch_odoo_cc(mock_client)


# ---------------------------------------------------------------------------
# Helper that builds a minimal active CC row
# ---------------------------------------------------------------------------


def _cc(id_, code, company_id, nombre="CC test", active=True, root_plan_id=None):
    """Return a dict that mimics a BigQuery row (subscript-accessible)."""
    return {
        "id": id_,
        "nombre": nombre,
        "code": code,
        "company_id": company_id,
        "active": active,
        "root_plan_id": root_plan_id,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFetchOdooCCDuplicateCodes:
    """
    Issue #5 regression: two active CCs with the same code but different company_id
    must both appear in the returned by_code dict.
    """

    def test_5_sync_cc_duplicate_codes_regression(self):
        """
        Regression: codes 616 and 619 are shared by company-6 (lower id) and company-2
        (PIMENTONES 26-27).  Both must appear in by_code with distinct id_cc keys.
        """
        rows = [
            # company-6 CCs that historically held codes 616 and 619
            _cc(297, "616", 6, "CARRO DE ARRASTRE NEGRO"),
            _cc(299, "619", 6, "GRUA HORQUILLA CLARK"),
            # PIMENTONES 26-27 company-2 CCs that were previously dropped
            _cc(733, "616", 2, "MT PIM.ROJO TEMP 26-27"),
            _cc(736, "619", 2, "AL1 PIM.ROJO TEMP 26-27"),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)

        # Canonical slots (lower company_id = 2 sorts first, but wait — we sort by company_id ASC,
        # so company-2 has lower company_id and wins the bare code slot).
        # company_id 2 < 6, so company-2 CCs get bare codes; company-6 CCs get "-c6" suffix.
        assert "616" in by_code, (
            "Company-2 CC (lower company_id) must occupy bare code 616"
        )
        assert "619" in by_code, (
            "Company-2 CC (lower company_id) must occupy bare code 619"
        )
        assert "616-c6" in by_code, "Company-6 CC must get suffixed id_cc 616-c6"
        assert "619-c6" in by_code, "Company-6 CC must get suffixed id_cc 619-c6"

        # Verify the right Odoo IDs are assigned
        assert by_code["616"]["id"] == "733"
        assert by_code["616-c6"]["id"] == "297"
        assert by_code["619"]["id"] == "736"
        assert by_code["619-c6"]["id"] == "299"

    def test_unique_code_unchanged(self):
        """A CC with a unique code must appear with its bare code as id_cc."""
        rows = [_cc(100, "500", 3, "CEREZOS SANTINA")]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert "500" in by_code
        assert by_code["500"]["id"] == "100"
        assert "500-c3" not in by_code

    def test_no_code_cc_excluded(self):
        """Active CCs with code=None must not appear in by_code."""
        rows = [
            _cc(531, None, 2, "ADMIN. ISLA DE MAIPO"),
            _cc(100, "200", 2, "Normal CC"),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert len(by_code) == 1
        assert "200" in by_code

    def test_three_companies_same_code(self):
        """
        Three companies with the same code: company with lowest company_id gets bare code,
        the other two get suffixed ids.
        """
        rows = [
            _cc(10, "999", 5, "CC empresa 5"),
            _cc(20, "999", 2, "CC empresa 2"),
            _cc(30, "999", 7, "CC empresa 7"),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        # company_id 2 is lowest → gets bare "999"
        assert by_code["999"]["id"] == "20"
        assert by_code["999-c5"]["id"] == "10"
        assert by_code["999-c7"]["id"] == "30"
        assert len(by_code) == 3

    def test_archived_cc_excluded_from_by_code(self):
        """Archived (active=False) CCs must not appear in by_code."""
        rows = [
            _cc(50, "300", 2, "Old CC", active=False),
            _cc(51, "301", 2, "Active CC", active=True),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert "300" not in by_code
        assert "301" in by_code

    def test_cross_farm_isolation(self):
        """
        CCs from company-3 (Zuñiga farm) must not interfere with company-2 (Isla de Maipo)
        when their codes are different.
        """
        rows = [
            _cc(200, "100", 2, "CC Isla de Maipo"),
            _cc(300, "200", 3, "CC Zuñiga"),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert by_code["100"]["company_id"] == 2
        assert by_code["200"]["company_id"] == 3
