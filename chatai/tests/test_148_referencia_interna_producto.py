"""
Regression tests for issue #148: add `referencia_interna` and
`producto_con_referencia` to BigQuery view vw_apuntes_analiticos_desglosados.

referencia_interna comes from Producto.default_code via the same JOIN already
used to compute `producto` (p.id = ad.product_id). Coverage is low (~3% of
rows) because the catalog only has ~96 templates vs ~2,100 distinct
product_id. producto_con_referencia concatenates referencia_interna with
producto, falling back to producto alone when there is no referencia_interna.

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


def _sql_source() -> str:
    return SQL_FILE.read_text(encoding="utf-8")


class TestIssue148ReferenciaInternaProducto:
    """Regression: persisted view SQL must expose referencia_interna and
    producto_con_referencia without breaking the producto column added in #144."""

    def test_148_sql_file_exists(self):
        assert SQL_FILE.exists(), f"Missing SQL file: {SQL_FILE}"

    def test_148_adds_referencia_interna_column(self):
        src = _sql_source()
        assert "AS referencia_interna" in src
        assert "p.default_code" in src

    def test_148_adds_producto_con_referencia_column(self):
        src = _sql_source()
        assert "AS producto_con_referencia" in src
        assert "cp.referencia_interna" in src
        assert "cp.producto" in src

    def test_148_producto_con_referencia_falls_back_to_producto(self):
        """When there is no referencia_interna, producto_con_referencia must equal producto."""
        src = _sql_source()
        assert "ELSE cp.producto" in src

    def test_148_preserves_producto_column_logic(self):
        """Issue #144's producto column (catalog vs cleaned label fallback) must still exist."""
        src = _sql_source()
        assert "_producto_catalogo" in src
        assert "_producto_etiqueta" in src
        assert "AS producto" in src

    def test_148_preserves_existing_consumer_columns(self):
        src = _sql_source()
        for col in (
            "product_id",
            "producto",
            "balance_asignado",
            "empresa_nombre",
            "cc_nombre",
            "cc_codigo",
            "cc_activo",
            "distribucion_resuelta",
        ):
            assert col in src, f"View must keep existing column {col}"

    def test_148_sql_still_creates_view(self):
        src = _sql_source()
        assert "CREATE OR REPLACE VIEW" in src
        assert (
            "`ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`" in src
        )
