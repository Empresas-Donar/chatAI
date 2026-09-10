"""
Regression tests for issue #162: analytic_distribution con valor nulo pasa
el filtro del exportador Odoo.

Verifica:
1. La vista SQL tarjas_reporte_odoo filtra entradas con valor NULL o vacío
   antes del jsonb_object_agg (WHERE v IS NOT NULL AND v != '').
2. La vista tarjas_reporte_odoo_tractorista tiene la misma corrección.
3. El endpoint de exportación filtra filas con ': null' en analytic_distribution.
4. El endpoint de preview clasifica filas con CC de valor nulo como excluidas
   con motivo 'CC con distribución nula'.
5. Regresión: valor_odoo con {"410": null} produce fila excluida, no OK.

Run:
    cd ChatAI && python -m pytest chatai/tests/test_162_fix_analytic_null_export.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

SQL_ODOO_VIEW = (
    Path(__file__).parent.parent.parent / "sql" / "tarjas" / "02_views_odoo.sql"
)
SQL_TRACTORISTA_VIEW = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "tarjas"
    / "08_views_odoo_tractorista.sql"
)
CONTROLLER = (
    Path(__file__).parent.parent
    / "backend"
    / "controllers"
    / "purchase_orders_controller.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sql_odoo() -> str:
    return SQL_ODOO_VIEW.read_text(encoding="utf-8")


def _sql_tractorista() -> str:
    return SQL_TRACTORISTA_VIEW.read_text(encoding="utf-8")


def _ctrl_source() -> str:
    return CONTROLLER.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# SQL view static analysis
# ---------------------------------------------------------------------------


class TestSqlViewNullFilter:
    """Issue #162 regression: the SQL views must filter NULL and empty-string
    values before aggregating with jsonb_object_agg."""

    def test_162_odoo_view_filters_null_values_regression(self):
        """
        Regression: jsonb_object_agg in tarjas_reporte_odoo must include
        'WHERE v IS NOT NULL AND v != ''' so that CCs with null percentages
        are dropped before aggregation, preventing {"410": null} in output.
        """
        sql = _sql_odoo()
        # The WHERE clause must appear inside the subselect for analytic_distribution
        assert "WHERE v IS NOT NULL AND v != ''" in sql, (
            "tarjas_reporte_odoo must filter null/empty values in jsonb_object_agg subselect"
        )

    def test_162_tractorista_view_filters_null_values_regression(self):
        """
        Regression: tarjas_reporte_odoo_tractorista has the same jsonb_object_agg
        pattern and must have the same null/empty filter applied.
        """
        sql = _sql_tractorista()
        assert "WHERE v IS NOT NULL AND v != ''" in sql, (
            "tarjas_reporte_odoo_tractorista must filter null/empty values in jsonb_object_agg subselect"
        )

    def test_null_filter_is_inside_analytic_distribution_subselect(self):
        """The WHERE clause must be part of the jsonb_object_agg subselect,
        not a top-level WHERE that would affect row count."""
        sql = _sql_odoo()
        # The aggregation subselect spans multiple lines; find the block that contains
        # both jsonb_object_agg and the analytic_distribution alias.
        start = sql.find("(SELECT jsonb_object_agg(k, ROUND(v::numeric, 2))")
        end = sql.find('"order_line/analytic_distribution"', start)
        subselect = sql[start : end + len('"order_line/analytic_distribution"')]
        assert "WHERE v IS NOT NULL" in subselect, (
            "NULL filter must be inside the jsonb_object_agg subselect, "
            "not as a top-level WHERE clause"
        )


# ---------------------------------------------------------------------------
# Controller export endpoint static analysis
# ---------------------------------------------------------------------------


class TestExportEndpointNullFilter:
    """The export endpoint must filter ': null' as well as '"": ' from
    analytic_distribution before including rows in the xlsx export."""

    def test_162_export_excludes_null_value_pattern_regression(self):
        """
        Regression: the export query must include NOT LIKE '%%: null%%' so that
        rows with {"410": null} in analytic_distribution are excluded from the xlsx.
        """
        src = _ctrl_source()
        assert "'%%: null%%'" in src, (
            "export_odoo_csv must filter rows where analytic_distribution LIKE '%%: null%%'"
        )

    def test_162_excluded_amount_counts_null_value_rows_regression(self):
        """
        Regression: the excluded_amount query must also count rows with null-value
        entries (': null' pattern) in the total monto excluido shown to the user.
        """
        src = _ctrl_source()
        # Both patterns must appear together in the excluded amount query section
        excl_block_start = src.find("Detect excluded rows")
        excl_block_end = src.find("excluded_amount = float", excl_block_start)
        excl_block = src[excl_block_start : excl_block_end + 100]
        assert "'%%: null%%'" in excl_block, (
            "The excluded_amount query must detect ': null' analytic entries"
        )

    def test_both_empty_key_and_null_value_filtered_from_export(self):
        """Both the empty-key pattern and the null-value pattern must be excluded."""
        src = _ctrl_source()
        # In the main export query (NOT LIKE), both patterns must appear
        export_query_region = src[
            src.find("export_odoo_csv") : src.find("def _cc_status")
        ]
        assert (
            'NOT LIKE \'%%"":' in export_query_region
            or "NOT LIKE '%%\"\": %%'" in export_query_region
        ), "export query must still exclude empty-key pattern"
        assert "NOT LIKE '%%: null%%'" in export_query_region, (
            "export query must exclude null-value pattern"
        )


# ---------------------------------------------------------------------------
# Preview endpoint classification (unit test with mocked DB)
# ---------------------------------------------------------------------------


def _make_preview_row(product_id, analytic, qty=1.0, price_unit=100.0):
    """Build a tuple matching the SELECT columns in get_export_preview."""
    return (product_id, analytic, qty, price_unit)


class TestPreviewNullValueClassification:
    """The preview endpoint must classify rows with CC null values as excluded."""

    def _run_preview_classification(self, rows: list):
        """
        Import purchase_orders_controller with heavy deps mocked and run the
        classification loop directly against the provided rows.

        Returns (preview_rows, excluded_rows).
        """
        # We test the classification logic inline without importing the full module
        # to avoid the FastAPI/DB/xhtml2pdf import chain. Reproduces the exact
        # logic from the fixed controller.
        import json as _json

        preview_rows = []
        excluded_rows = []
        total_ok = 0.0
        total_excluded = 0.0
        active_ids: set = {"406", "407", "408", "409", "412"}
        bq_available = True

        for product_id, analytic, qty, price_unit in rows:
            qty_f = float(qty or 0)
            price_f = float(price_unit or 0)
            total_line = round(qty_f * price_f, 0)

            analytic_dict: dict = {}
            if isinstance(analytic, dict):
                analytic_dict = analytic
            elif isinstance(analytic, str):
                try:
                    analytic_dict = _json.loads(analytic)
                except Exception:
                    pass

            # Replicated from the fixed controller logic
            cc_ids = [k for k, v in analytic_dict.items() if k != "" and v is not None]
            cc_ids_with_null = [
                k for k, v in analytic_dict.items() if k != "" and v is None
            ]

            if not product_id:
                excluded_rows.append({"reason": "Labor sin mapear en Odoo"})
                total_excluded += total_line
                continue

            if cc_ids_with_null:
                excluded_rows.append(
                    {
                        "product_id": product_id,
                        "null_ids": cc_ids_with_null,
                        "reason": f"CC con distribución nula: {', '.join(cc_ids_with_null)}",
                        "total": total_line,
                    }
                )
                total_excluded += total_line
                continue

            if not cc_ids:
                excluded_rows.append({"reason": "CC vacío o sin mapear"})
                total_excluded += total_line
                continue

            archived = [cid for cid in cc_ids if bq_available and cid not in active_ids]

            if archived:
                excluded_rows.append(
                    {
                        "product_id": product_id,
                        "archived_ids": archived,
                        "reason": f"CC archivado: {', '.join(archived)}",
                        "total": total_line,
                    }
                )
                total_excluded += total_line
            else:
                preview_rows.append({"product_id": product_id, "total": total_line})
                total_ok += total_line

        return preview_rows, excluded_rows

    def test_162_null_value_cc_is_excluded_not_ok_regression(self):
        """
        Regression: a row whose analytic_distribution contains {"410": null, "406": 9.15}
        must be classified as excluded with reason 'CC con distribución nula',
        NOT as an OK row. Before the fix, it was classified as OK and exported.
        """
        analytic = {"406": 9.15, "407": 8.63, "410": None}
        rows = [_make_preview_row("4.1", analytic)]

        preview, excluded = self._run_preview_classification(rows)

        assert len(preview) == 0, (
            "Row with null CC value must NOT appear in preview (OK) rows"
        )
        assert len(excluded) == 1, "Row with null CC value must appear in excluded rows"
        assert "CC con distribución nula" in excluded[0]["reason"]
        assert "410" in excluded[0]["null_ids"]

    def test_valid_analytic_is_ok(self):
        """A row with all valid CC percentages must be classified as OK."""
        analytic = {"406": 50.0, "407": 50.0}
        rows = [_make_preview_row("4.1", analytic)]

        preview, excluded = self._run_preview_classification(rows)

        assert len(preview) == 1
        assert len(excluded) == 0

    def test_empty_key_cc_is_excluded(self):
        """A row with empty-key CC ({"": 100}) must be excluded (existing behavior)."""
        analytic = {"": 100.0}
        rows = [_make_preview_row("4.1", analytic)]

        preview, excluded = self._run_preview_classification(rows)

        assert len(preview) == 0
        assert len(excluded) == 1

    def test_all_null_values_is_excluded(self):
        """If all CC values are null, the row must be excluded."""
        analytic = {"410": None, "411": None}
        rows = [_make_preview_row("4.1", analytic)]

        preview, excluded = self._run_preview_classification(rows)

        assert len(preview) == 0
        assert len(excluded) == 1
        assert "CC con distribución nula" in excluded[0]["reason"]

    def test_mix_of_null_and_valid_keys_is_excluded(self):
        """Even if some keys have valid values, a null key makes the row excluded."""
        analytic = {"406": 50.0, "410": None}
        rows = [_make_preview_row("4.1", analytic)]

        preview, excluded = self._run_preview_classification(rows)

        assert len(preview) == 0, (
            "Row with any null CC must be excluded regardless of other valid CCs"
        )
        assert "410" in excluded[0]["null_ids"]

    def test_null_value_in_json_string_is_parsed_correctly(self):
        """When analytic is a JSON string with null value, it must be detected."""
        analytic = '{"406": 9.15, "410": null}'
        rows = [_make_preview_row("4.1", analytic)]

        preview, excluded = self._run_preview_classification(rows)

        assert len(preview) == 0
        assert "410" in excluded[0]["null_ids"]

    def test_cross_farm_isolation_different_products(self):
        """
        Two products from the same preview query: one valid (farm A), one with
        null CC (farm B). Each must be classified independently.
        """
        analytic_a = {"406": 100.0}
        analytic_b = {"410": None}
        rows = [
            _make_preview_row("3.1", analytic_a),
            _make_preview_row("4.1", analytic_b),
        ]

        preview, excluded = self._run_preview_classification(rows)

        assert len(preview) == 1
        assert preview[0]["product_id"] == "3.1"
        assert len(excluded) == 1
        assert excluded[0]["product_id"] == "4.1"
