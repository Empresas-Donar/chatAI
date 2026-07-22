"""
tests/test_sync_cc.py
---------------------
Regression tests for apps/sync_cc.py:
  - id_cc deduplication logic (issue #5)
  - Modelos_Distribucion_Analitica sync (issue #7)

No BigQuery or PostgreSQL connection is required; all tests are pure-unit against
the in-process functions via direct import.
"""

import sys
from pathlib import Path
from typing import Optional
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


# ---------------------------------------------------------------------------
# Helpers for issue #7 — Modelos_Distribucion_Analitica
# ---------------------------------------------------------------------------


def _model_row(
    id_: int,
    numeracion: str,
    analytic_distribution: str,
    company_id: int,
    analytic_distribution_code_id: Optional[int] = None,
) -> dict:
    """Return a dict mimicking a BigQuery row from Modelos_Distribucion_Analitica."""
    return {
        "id": str(id_),
        "x_studio_numeracin": numeracion,
        "analytic_distribution": analytic_distribution,
        "company_id": str(company_id),
        "analytic_distribution_code_id": str(analytic_distribution_code_id) if analytic_distribution_code_id else None,
    }


def _run_fetch_distribucion_models(model_rows: list[dict], by_code: dict):
    """
    Import fetch_odoo_distribucion_models and call it with a mock BQ client
    and the provided by_code dict.  Returns list of dicts ready to insert.
    """
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

        importlib.reload(sync_cc)

        mock_client = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.result.return_value = iter(model_rows)
        mock_client.query.return_value = mock_query_result

        return sync_cc.fetch_odoo_distribucion_models(mock_client, by_code)


class TestSyncDistribucionModels:
    """
    Issue #7 regression: Modelos_Distribucion_Analitica must be synced into tarjas_cc
    using x_studio_numeracin as id_cc and analytic_distribution as valor_odoo.
    """

    def test_7_sync_distribucion_analitica_regression(self):
        """
        Regression: model 632 (PIMENTONES AL1 26/27) distributes 9.6% to CC 735 and
        90.4% to CC 736.  After fetch, the model must appear in the result with:
          - id_cc = "632"
          - valor_odoo = '{"735": 9.6, "736": 90.4}'
          - cultivo resolved from by_code via x_studio_numeracin or fallback
        """
        by_code = {
            "735": {"id": "1001", "nombre": "AL1 PIM.ROJO TEMP 26-27", "company_id": 2},
            "736": {"id": "1002", "nombre": "AL2 PIM.AMARILLO TEMP 26-27", "company_id": 2},
        }
        rows = [
            _model_row(
                id_=91,
                numeracion="632",
                analytic_distribution='{"735": 9.6, "736": 90.4}',
                company_id=2,
                analytic_distribution_code_id=272,
            )
        ]
        result = _run_fetch_distribucion_models(rows, by_code)

        assert len(result) == 1
        model = result[0]
        assert model["id_cc"] == "632"
        assert model["valor_odoo"] == '{"735": 9.6, "736": 90.4}'
        # cultivo: no CC has code "632" in by_code, no id match for 272 → fallback to numeracion
        assert model["cultivo"] == "632"

    def test_cultivo_resolved_by_code_match(self):
        """
        When a CC exists in by_code whose key equals x_studio_numeracin,
        its nombre is used as cultivo.
        """
        by_code = {
            "270": {"id": "131", "nombre": "Administraciones Donar", "company_id": 1},
        }
        rows = [
            _model_row(
                id_=1,
                numeracion="270",
                analytic_distribution='{"131": 100.0}',
                company_id=1,
                analytic_distribution_code_id=22,
            )
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        assert result[0]["cultivo"] == "Administraciones Donar"

    def test_cultivo_resolved_by_odoo_id_fallback(self):
        """
        When no CC code matches x_studio_numeracin but analytic_distribution_code_id
        matches an Odoo id in by_code, that nombre is used as cultivo.
        """
        by_code = {
            # CC with odoo id "251" has code "653", so code "428" won't match
            "653": {"id": "251", "nombre": "CARRO DESPARRAMADOR N 7", "company_id": 3},
        }
        rows = [
            _model_row(
                id_=86,
                numeracion="428",
                analytic_distribution='{"724": 50.0, "725": 50.0}',
                company_id=3,
                analytic_distribution_code_id=251,
            )
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        assert result[0]["cultivo"] == "CARRO DESPARRAMADOR N 7"

    def test_cultivo_fallback_to_numeracion(self):
        """
        When no CC name can be resolved, cultivo falls back to x_studio_numeracin.
        """
        by_code: dict = {}
        rows = [
            _model_row(
                id_=99,
                numeracion="999",
                analytic_distribution='{"500": 100.0}',
                company_id=2,
                analytic_distribution_code_id=None,
            )
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        assert result[0]["cultivo"] == "999"

    def test_model_without_numeracion_is_skipped(self):
        """Models with empty x_studio_numeracin must be skipped."""
        by_code: dict = {}
        rows = [
            {
                "id": "50",
                "x_studio_numeracin": "",
                "analytic_distribution": '{"100": 100.0}',
                "company_id": "2",
                "analytic_distribution_code_id": None,
            }
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        assert len(result) == 0

    def test_id_campo_derived_from_company_id(self):
        """company_id must be mapped to id_campo via COMPANY_TO_CAMPO."""
        by_code: dict = {}
        rows = [
            _model_row(99, "500", '{"100": 100.0}', company_id=2),
            _model_row(100, "501", '{"101": 100.0}', company_id=3),
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        # COMPANY_TO_CAMPO: {1: 1, 2: 1, 3: 2, 5: 3, 6: 4, 7: 4}
        assert result[0]["id_campo"] == 1   # company_id=2 → campo 1
        assert result[1]["id_campo"] == 2   # company_id=3 → campo 2

    def test_multiple_models_all_returned(self):
        """All models with valid numeracin must be present in the result."""
        by_code: dict = {}
        rows = [
            _model_row(91, "632", '{"735": 9.6, "736": 90.4}', company_id=2),
            _model_row(92, "633", '{"737": 9.6, "738": 90.4}', company_id=2),
            _model_row(90, "639", '{"733": 0.7, "736": 13.97}', company_id=2),
            _model_row(82, "1500", '{"122": 26.9, "395": 5.92}', company_id=2),
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        ids = {m["id_cc"] for m in result}
        assert ids == {"632", "633", "639", "1500"}
