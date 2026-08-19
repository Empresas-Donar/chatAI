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
from unittest.mock import MagicMock, patch

# Make the apps/ directory importable without installing the package.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps"))


def _make_rows(specs: list[dict]) -> list[dict]:
    """Build mock BigQuery row objects from dicts (subscript-accessible like real BQ rows)."""
    return list(specs)


def _load_sync_cc():
    """
    Import (or reload) sync_cc with heavy deps mocked, returning the module itself.
    Useful for tests that call plain-Python helpers (e.g. _resolve_campo) directly
    rather than going through fetch_odoo_cc/fetch_odoo_distribucion_models.
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
        return sync_cc


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


def _cc(
    id_,
    code,
    company_id,
    nombre="CC test",
    active=True,
    root_plan_id=None,
    plan_id=None,
):
    """Return a dict that mimics a BigQuery row (subscript-accessible)."""
    return {
        "id": id_,
        "nombre": nombre,
        "code": code,
        "company_id": company_id,
        "active": active,
        "root_plan_id": root_plan_id,
        "plan_id": plan_id,
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
        Regression: codes 616 and 619 are shared by company-3 (Zuñiga) and company-2
        (PIMENTONES 26-27) — both allowed companies.  Both must appear in by_code with
        distinct id_cc keys.

        (Originally company-6 stood in for the higher-company_id side of this collision,
        but issue #90 excludes company-6 from the sync entirely — see
        TestFetchOdooCCCompanyAllowlist for that regression — so this test now uses
        company-3, another allowed company, to keep exercising the dedup/suffix logic.)
        """
        rows = [
            # company-3 CCs that share codes 616 and 619 with company-2
            _cc(297, "616", 3, "CARRO DE ARRASTRE NEGRO"),
            _cc(299, "619", 3, "GRUA HORQUILLA CLARK"),
            # PIMENTONES 26-27 company-2 CCs that were previously dropped
            _cc(733, "616", 2, "MT PIM.ROJO TEMP 26-27"),
            _cc(736, "619", 2, "AL1 PIM.ROJO TEMP 26-27"),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)

        # Canonical slots: we sort by company_id ASC, so company-2 (lower) wins the bare
        # code slot and company-3 (higher) gets the "-c3" suffix.
        assert "616" in by_code, (
            "Company-2 CC (lower company_id) must occupy bare code 616"
        )
        assert "619" in by_code, (
            "Company-2 CC (lower company_id) must occupy bare code 619"
        )
        assert "616-c3" in by_code, "Company-3 CC must get suffixed id_cc 616-c3"
        assert "619-c3" in by_code, "Company-3 CC must get suffixed id_cc 619-c3"

        # Verify the right Odoo IDs are assigned
        assert by_code["616"]["id"] == "733"
        assert by_code["616-c3"]["id"] == "297"
        assert by_code["619"]["id"] == "736"
        assert by_code["619-c3"]["id"] == "299"

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


class TestFetchOdooCCCompanyAllowlist:
    """
    Issue #90 regression: only CC from Agrícola Donar Uno/Dos and Kontrolag
    (company_id in {1, 2, 3, 5, 7}) may be synced into tarjas_cc. CC from any other
    Odoo company (e.g. company_id 6 "FB", or 9/11/12/15 unrelated holding shells)
    must never reach `by_code`, regardless of whether their code collides with an
    allowed company's code.
    """

    def test_90_cc_sync_company_filter_regression(self):
        """
        Regression: company_id=6 (unrelated "FB" equipment company, historically
        mis-mapped to campo 4/Kontrolag) must be excluded even though company_id=7
        (the real Kontrolag) is allowed.
        """
        rows = [
            _cc(297, "616", 6, "CARRO DE ARRASTRE NEGRO"),  # excluded company
            _cc(1, "K0001", 7, "KONTROLAG"),  # real Kontrolag
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert "616" not in by_code, "company_id=6 CC must be excluded from sync"
        assert "K0001" in by_code, "company_id=7 (Kontrolag) CC must still sync"
        assert by_code["K0001"]["company_id"] == 7

    def test_excluded_company_does_not_steal_bare_code(self):
        """
        An excluded company must not participate in the (code, company_id) dedup
        ranking at all — an allowed company sharing the same code must always get
        the bare code, never a "-cN" suffix caused by a filtered-out competitor.
        """
        rows = [
            _cc(10, "999", 9, "CC empresa 9 (excluida)"),
            _cc(20, "999", 2, "CC empresa 2 (permitida)"),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert by_code["999"]["id"] == "20"
        assert "999-c9" not in by_code
        assert len(by_code) == 1

    def test_all_allowed_companies_pass_through(self):
        """Every company_id in ALLOWED_COMPANY_IDS (1, 2, 3, 5, 7) must sync unaffected."""
        rows = [
            _cc(1, "100", 1, "CC empresa 1"),
            _cc(2, "200", 2, "CC empresa 2"),
            _cc(3, "300", 3, "CC empresa 3"),
            _cc(4, "400", 5, "CC empresa 5"),
            _cc(5, "500", 7, "CC empresa 7"),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert set(by_code.keys()) == {"100", "200", "300", "400", "500"}

    def test_disallowed_companies_excluded(self):
        """Companies 6, 9, 11, 12, 15 (confirmed unrelated to Donar/Kontrolag) are excluded."""
        rows = [
            _cc(1, "601", 6, "VENTA REPUESTOS (FB)"),
            _cc(2, "260", 9, "INVERSIONES DONAR"),
            _cc(3, "700", 11, "INVERSIONES SAN JUAN"),
            _cc(4, "201", 12, "FD SPA"),
            _cc(5, "478", 15, "VIVEROS"),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert by_code == {}

    def test_archived_cc_from_excluded_company_ignored(self):
        """Archived CCs from an excluded company must not generate replacement entries."""
        rows = [
            _cc(50, "300", 6, "Old CC empresa 6", active=False),
            _cc(51, "300", 2, "Active CC empresa 2", active=True),
        ]
        by_code, archived_to_replacements = _run_fetch_odoo_cc(rows)
        assert "300" in by_code
        assert by_code["300"]["company_id"] == 2
        assert archived_to_replacements == {}


# ---------------------------------------------------------------------------
# Helpers for issue #7 — Modelos_Distribucion_Analitica
# ---------------------------------------------------------------------------


def _model_row(
    id_: int,
    numeracion: str,
    analytic_distribution: str,
    company_id: int,
    analytic_distribution_code_id: int | None = None,
) -> dict:
    """Return a dict mimicking a BigQuery row from Modelos_Distribucion_Analitica."""
    return {
        "id": str(id_),
        "x_studio_numeracin": numeracion,
        "analytic_distribution": analytic_distribution,
        "company_id": str(company_id),
        "analytic_distribution_code_id": str(analytic_distribution_code_id)
        if analytic_distribution_code_id
        else None,
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
            "736": {
                "id": "1002",
                "nombre": "AL2 PIM.AMARILLO TEMP 26-27",
                "company_id": 2,
            },
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
        """
        company_id must be mapped to id_campo via the flat COMPANY_TO_CAMPO for every
        company_id other than 3 (which splits by plan_id — see
        TestCompany3PlanSplitDistribucionModels below, issue #90 follow-up).
        """
        by_code: dict = {}
        rows = [
            _model_row(99, "500", '{"100": 100.0}', company_id=2),
            _model_row(100, "501", '{"101": 100.0}', company_id=5),
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        # COMPANY_TO_CAMPO: {1: 1, 2: 1, 3: 3 (superseded for models, see below), 5: 3, 7: 4}
        assert result[0]["id_campo"] == 1  # company_id=2 → campo 1
        assert result[1]["id_campo"] == 3  # company_id=5 → campo 3 (Zuñiga)

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


class TestSyncDistribucionModelsRefresh:
    """
    Issue #126 regression: sync_distribucion_models must refresh (UPDATE) an existing
    tarjas_cc row whose stored valor_odoo still references an archived CC id, instead
    of silently skipping it via ON CONFLICT (id_cc) DO NOTHING. Under the old
    insert-only behavior, a row created once from an Odoo distribution model never
    picked up later changes (including CCs being archived), so archived CC ids
    accumulated in tarjas_cc indefinitely until someone clicked "Sync CC" manually —
    and even then only individual ids with a confident fuzzy replacement got fixed.
    """

    def _mock_conn(self, existing_rows: list[tuple[str, dict]]):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = existing_rows
        return mock_conn, mock_cursor

    def _update_calls(self, mock_cursor):
        return [
            c
            for c in mock_cursor.execute.call_args_list
            if "UPDATE appsheet.tarjas_cc" in c.args[0]
        ]

    def _insert_calls(self, mock_cursor):
        return [
            c
            for c in mock_cursor.execute.call_args_list
            if "INSERT INTO appsheet.tarjas_cc" in c.args[0]
        ]

    def test_126_stale_archived_row_gets_refreshed_regression(self):
        """
        id_cc "210" currently stores {"604": 50.0, "395": 50.0}; 604 is archived.
        The matching model's fresh Odoo distribution must overwrite valor_odoo.
        """
        sync_cc = _load_sync_cc()
        mock_conn, mock_cursor = self._mock_conn([("210", {"604": 50.0, "395": 50.0})])
        models = [
            {
                "id_cc": "210",
                "cultivo": "210",
                "id_campo": 1,
                "valor_odoo": '{"395": 100.0, "759": 9.09}',
            }
        ]
        sync_cc.sync_distribucion_models(models, {"395", "759"}, mock_conn)

        updates = self._update_calls(mock_cursor)
        assert len(updates) == 1
        _sql, params = updates[0].args
        assert params == ('{"395": 100.0, "759": 9.09}', "210")

    def test_row_without_archived_reference_is_left_untouched(self):
        """An existing row whose CC ids are all still active must not be rewritten."""
        sync_cc = _load_sync_cc()
        mock_conn, mock_cursor = self._mock_conn([("639", {"733": 100.0})])
        models = [
            {
                "id_cc": "639",
                "cultivo": "639",
                "id_campo": 1,
                "valor_odoo": '{"733": 100.0}',
            }
        ]
        sync_cc.sync_distribucion_models(models, {"733"}, mock_conn)
        assert self._update_calls(mock_cursor) == []

    def test_new_id_cc_still_inserted(self):
        """A model with no existing tarjas_cc row must still be inserted, as before."""
        sync_cc = _load_sync_cc()
        mock_conn, mock_cursor = self._mock_conn([])
        models = [
            {
                "id_cc": "999",
                "cultivo": "Nuevo cultivo",
                "id_campo": 1,
                "valor_odoo": '{"100": 100.0}',
            }
        ]
        sync_cc.sync_distribucion_models(models, {"100"}, mock_conn)
        assert len(self._insert_calls(mock_cursor)) == 1
        assert self._update_calls(mock_cursor) == []

    def test_empty_stored_distribution_is_not_treated_as_archived(self):
        """A row whose valor_odoo has no keys (empty {}) must not trigger a refresh."""
        sync_cc = _load_sync_cc()
        mock_conn, mock_cursor = self._mock_conn([("210", {})])
        models = [
            {
                "id_cc": "210",
                "cultivo": "210",
                "id_campo": 1,
                "valor_odoo": '{"395": 100.0}',
            }
        ]
        sync_cc.sync_distribucion_models(models, {"395"}, mock_conn)
        assert self._update_calls(mock_cursor) == []


class TestFetchDistribucionModelsCompanyAllowlist:
    """
    Issue #90 regression: fetch_odoo_distribucion_models must apply the same
    ALLOWED_COMPANY_IDS filter as fetch_odoo_cc — models from company_id=6 ("FB")
    or other unrelated companies must never be synced as virtual CCs.
    """

    def test_90_distribucion_models_company_filter_regression(self):
        by_code: dict = {}
        rows = [
            _model_row(1, "601", '{"1": 100.0}', company_id=6),  # excluded (FB)
            _model_row(2, "K0050", '{"2": 100.0}', company_id=7),  # allowed (Kontrolag)
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        ids = {m["id_cc"] for m in result}
        assert ids == {"K0050"}

    def test_disallowed_companies_excluded_from_models(self):
        by_code: dict = {}
        rows = [
            _model_row(1, "260", '{"1": 100.0}', company_id=9),
            _model_row(2, "700", '{"2": 100.0}', company_id=11),
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        assert result == []


# ---------------------------------------------------------------------------
# Issue #90 follow-up: company_id=3 splits across Isla de Maipo / Zuñiga by plan_id
# ---------------------------------------------------------------------------


class TestResolveCampoCompany3PlanSplit:
    """
    Issue #90 follow-up regression: company_id=3 ("Agrícola Donar Dos") CC do not all
    belong to campo 3 (Zuñiga) — plan_id splits them between Isla de Maipo (campo 2)
    and Zuñiga (campo 3). An unrecognized plan_id under company_id=3 must not be
    silently guessed into either campo.
    """

    def test_company_3_isla_de_maipo_plan_id_maps_to_campo_2(self):
        sync_cc = _load_sync_cc()
        # 247 is in COMPANY_3_ISLA_DE_MAIPO_PLAN_IDS
        assert sync_cc._resolve_campo(3, "247") == 2
        # Also accepts a bare int, not just a string (BQ CAST(... AS STRING) usually
        # yields a str, but info dicts may be built with either).
        assert sync_cc._resolve_campo(3, 251) == 2

    def test_company_3_zuniga_plan_id_maps_to_campo_3(self):
        sync_cc = _load_sync_cc()
        # 255 is in COMPANY_3_ZUNIGA_PLAN_IDS
        assert sync_cc._resolve_campo(3, "255") == 3
        assert sync_cc._resolve_campo(3, 262) == 3

    def test_company_3_unrecognized_plan_id_does_not_silently_default(self, caplog):
        """
        A plan_id under company_id=3 outside both known clusters must NOT be silently
        assigned to Isla de Maipo (2) or Zuñiga (3) — it falls back to DEFAULT_CAMPO
        with a visible warning logged, so the gap gets noticed rather than misfiled.
        """
        sync_cc = _load_sync_cc()
        with caplog.at_level("WARNING"):
            result = sync_cc._resolve_campo(3, "999999")
        assert result == sync_cc.DEFAULT_CAMPO
        assert result not in (2, 3), (
            "unrecognized plan_id under company_id=3 must not resolve to either "
            "known campo without a trace in the logs"
        )
        assert any(
            "999999" in record.message and "no reconocido" in record.message
            for record in caplog.records
        ), "an unresolved company_id=3 plan_id must log a visible warning"

    def test_company_3_missing_plan_id_does_not_silently_default(self, caplog):
        """A missing/None plan_id under company_id=3 is unresolved, not a default guess."""
        sync_cc = _load_sync_cc()
        with caplog.at_level("WARNING"):
            result = sync_cc._resolve_campo(3, None)
        assert result == sync_cc.DEFAULT_CAMPO
        assert any("no reconocido" in record.message for record in caplog.records)

    def test_other_companies_unaffected_by_plan_id(self):
        """Non-company-3 ids keep using the flat COMPANY_TO_CAMPO regardless of plan_id."""
        sync_cc = _load_sync_cc()
        assert (
            sync_cc._resolve_campo(2, "247") == 1
        )  # plan_id ignored for company_id != 3
        assert sync_cc._resolve_campo(7, "255") == 4
        assert sync_cc._resolve_campo(5, None) == 3


class TestFetchOdooCCCompany3PlanId:
    """
    Issue #90 follow-up regression: fetch_odoo_cc must select and thread `plan_id`
    through into by_code, so downstream campo resolution (_resolve_campo) can split
    company_id=3 CC between Isla de Maipo and Zuñiga.
    """

    def test_plan_id_threaded_into_by_code(self):
        rows = [
            _cc(429, "CER-RP-23", 3, "CEREZOS RED PACIFIC 2023", plan_id=247),
            _cc(881, "CIR-ADU", 3, "CIRUELOS ADULTOS", plan_id=255),
        ]
        by_code, _ = _run_fetch_odoo_cc(rows)
        assert by_code["CER-RP-23"]["plan_id"] == "247"
        assert by_code["CIR-ADU"]["plan_id"] == "255"

    def test_resolved_campo_matches_expected_cluster(self):
        """
        End-to-end: a CC fetched via fetch_odoo_cc under company_id=3 resolves to the
        correct campo once run through _resolve_campo (what sync_tarjas_cc does).
        """
        sync_cc = _load_sync_cc()
        rows = [
            _cc(429, "CER-RP-23", 3, "CEREZOS RED PACIFIC 2023", plan_id=247),  # Isla
            _cc(881, "CIR-ADU", 3, "CIRUELOS ADULTOS", plan_id=255),  # Zuñiga
        ]
        mock_client = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.result.return_value = iter(rows)
        mock_client.query.return_value = mock_query_result
        by_code, _ = sync_cc.fetch_odoo_cc(mock_client)

        assert (
            sync_cc._resolve_campo(
                by_code["CER-RP-23"]["company_id"], by_code["CER-RP-23"]["plan_id"]
            )
            == 2
        )
        assert (
            sync_cc._resolve_campo(
                by_code["CIR-ADU"]["company_id"], by_code["CIR-ADU"]["plan_id"]
            )
            == 3
        )


class TestCompany3PlanSplitDistribucionModels:
    """
    Issue #90 follow-up regression: fetch_odoo_distribucion_models must resolve the
    Isla de Maipo / Zuñiga split for company_id=3 models even though the
    Modelos_Distribucion_Analitica table has no plan_id column of its own — it must
    borrow plan_id from the underlying CC (matched by code, by
    analytic_distribution_code_id, or from the analytic_distribution targets), and
    must not silently default when none of those resolve.
    """

    def test_plan_id_resolved_via_code_match(self):
        """Model whose numeracion matches a by_code entry inherits that CC's plan_id/campo."""
        by_code = {
            "451": {
                "id": "900",
                "nombre": "CIRUELAS D'AGEN 2025",
                "company_id": 3,
                "plan_id": "247",
            },
        }
        rows = [
            _model_row(
                1,
                "451",
                '{"900": 100.0}',
                company_id=3,
                analytic_distribution_code_id=900,
            ),
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        assert result[0]["id_campo"] == 2  # plan_id 247 → Isla de Maipo

    def test_plan_id_resolved_via_analytic_distribution_code_id_match(self):
        """Model resolved via analytic_distribution_code_id (not a direct code match)."""
        by_code = {
            "860": {
                "id": "700",
                "nombre": "CIRUELOS ADULTOS",
                "company_id": 3,
                "plan_id": "255",
            },
        }
        rows = [
            _model_row(
                2,
                "MOD-77",
                '{"700": 100.0}',
                company_id=3,
                analytic_distribution_code_id=700,
            ),
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        assert result[0]["id_campo"] == 3  # plan_id 255 → Zuñiga

    def test_plan_id_resolved_via_distribution_targets_when_no_direct_match(self):
        """
        When the model doesn't resolve a CC via numeracion/code_id directly, but every
        target in its analytic_distribution JSON unambiguously belongs to the same
        plan_id cluster, that plan_id is used.
        """
        by_code = {
            "429": {
                "id": "429",
                "nombre": "CEREZOS RED PACIFIC 2023",
                "company_id": 3,
                "plan_id": "247",
            },
            "430": {
                "id": "430",
                "nombre": "CEREZOS RED PACIFIC 2023 SUR",
                "company_id": 3,
                "plan_id": "247",
            },
        }
        rows = [
            _model_row(
                3,
                "MOD-99",
                '{"429": 50.0, "430": 50.0}',
                company_id=3,
                analytic_distribution_code_id=None,
            ),
        ]
        result = _run_fetch_distribucion_models(rows, by_code)
        assert (
            result[0]["id_campo"] == 2
        )  # both targets are plan_id 247 → Isla de Maipo

    def test_unresolvable_plan_id_does_not_silently_default(self, caplog):
        """
        A company_id=3 model with no code/id match and no resolvable distribution
        targets must not be silently assigned to Isla de Maipo or Zuñiga — it falls
        back to DEFAULT_CAMPO with a visible warning.
        """
        by_code: dict = {}
        rows = [
            _model_row(
                4,
                "MOD-UNKNOWN",
                '{"9999": 100.0}',
                company_id=3,
                analytic_distribution_code_id=None,
            ),
        ]
        with caplog.at_level("WARNING"):
            result = _run_fetch_distribucion_models(rows, by_code)
        assert result[0]["id_campo"] not in (2, 3)
        assert any("no reconocido" in record.message for record in caplog.records)

    def test_disagreeing_distribution_targets_do_not_silently_default(self, caplog):
        """
        If the distribution targets disagree on plan_id (one Isla, one Zuñiga), that's
        ambiguous — must not silently pick one, falls back with a warning instead.
        """
        by_code = {
            "429": {
                "id": "429",
                "nombre": "CEREZOS RED PACIFIC 2023",
                "company_id": 3,
                "plan_id": "247",
            },
            "860": {
                "id": "860",
                "nombre": "CIRUELOS ADULTOS",
                "company_id": 3,
                "plan_id": "255",
            },
        }
        rows = [
            _model_row(
                5,
                "MOD-AMBIGUOUS",
                '{"429": 50.0, "860": 50.0}',
                company_id=3,
                analytic_distribution_code_id=None,
            ),
        ]
        with caplog.at_level("WARNING"):
            result = _run_fetch_distribucion_models(rows, by_code)
        assert result[0]["id_campo"] not in (2, 3)
        assert any("no reconocido" in record.message for record in caplog.records)
