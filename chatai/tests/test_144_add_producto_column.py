"""
Regression tests for issue #144: add `producto` to BigQuery view
vw_apuntes_analiticos_desglosados and persist the DDL in git.

The live view lived only in BigQuery (ace-scarab-484515-v1.odoo_data) and
exposed product_id but not the Spanish product name. Variantes_del_producto
is not exported, so the SQL joins Producto.id = product_id and extracts
JSON_VALUE(name, '$.es_CL').

Tests are offline against the versioned SQL file so they do not depend on
BigQuery credentials.
"""

from pathlib import Path

SQL_FILE = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "bigquery"
    / "vw_apuntes_analiticos_desglosados.sql"
)

VIEW_NAME = "vw_apuntes_analiticos_desglosados"
FULL_VIEW_PATH = "`ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`"


def _sql_source() -> str:
    return SQL_FILE.read_text(encoding="utf-8")


class TestIssue144AddProductoColumn:
    """Regression: persisted view SQL must create the view with producto."""

    def test_144_add_producto_column_regression(self):
        """Would have failed when the view DDL was missing from git and had no producto."""
        src = _sql_source()
        assert "CREATE OR REPLACE VIEW" in src
        assert FULL_VIEW_PATH in src
        assert VIEW_NAME in src
        assert "AS producto" in src

    def test_144_sql_file_exists(self):
        assert SQL_FILE.exists(), f"Missing SQL file: {SQL_FILE}"

    def test_144_sql_joins_producto_catalog(self):
        src = _sql_source()
        assert "`ace-scarab-484515-v1.odoo_data.Producto`" in src
        assert "p.id = ad.product_id" in src

    def test_144_sql_extracts_spanish_product_name(self):
        src = _sql_source()
        assert "JSON_VALUE(p.name, '$.es_CL')" in src
        assert "JSON_VALUE(p.name, '$.en_US')" in src

    def test_144_sql_preserves_existing_consumer_columns(self):
        src = _sql_source()
        for col in (
            "product_id",
            "balance_asignado",
            "empresa_nombre",
            "cc_nombre",
            "cc_codigo",
            "cc_activo",
            "distribucion_resuelta",
        ):
            assert col in src, f"View must keep existing column {col}"

    def test_144_sql_keeps_analytic_explode_logic(self):
        src = _sql_source()
        assert "Reporte_Analitico" in src
        assert "Modelos_Distribucion_Analitica" in src
        assert "CC_analiticos" in src
        assert "UNNEST(REGEXP_EXTRACT_ALL" in src
