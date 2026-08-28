"""
Regression tests for issue #150: fix the variant-vs-template JOIN in
vw_apuntes_analiticos_desglosados.

product_id in Reporte_Analitico (and every other BigQuery export sourced from
account.move.line / stock.move / sale.order.line) is the Odoo VARIANT id
(product.product), not the template id (product.template) that Producto
exports. Issues #144 and #148 joined `Producto.id = product_id` directly,
which only matched by coincidence (~96 of ~2,100 distinct product_id).

Now that Variantes_del_producto (product.product) is exported to BigQuery,
the correct chain is:
  product_id -> Variantes_del_producto.id -> product_tmpl_id -> Producto.id

referencia_interna now prefers the variant-level default_code (exact match),
falls back to the template-level default_code, and finally to the bracket
code in `name` from #148 for products with no default_code in Odoo at all.

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


class TestIssue150FixVarianteTemplateJoin:
    def test_150_sql_file_exists(self):
        assert SQL_FILE.exists(), f"Missing SQL file: {SQL_FILE}"

    def test_150_joins_variantes_del_producto_by_product_id(self):
        src = _sql_source()
        assert "`ace-scarab-484515-v1.odoo_data.Variantes_del_producto`" in src
        assert "v.id = ad.product_id" in src

    def test_150_joins_producto_via_template_id_not_product_id(self):
        """Producto must be reached through the variant's product_tmpl_id,
        never through a direct match against the account.move.line product_id."""
        src = _sql_source()
        assert "p.id = v.product_tmpl_id" in src
        assert "p.id = ad.product_id" not in src

    def test_150_referencia_interna_prefers_variant_then_template_then_label(self):
        src = _sql_source()
        assert "NULLIF(TRIM(v.default_code), '')" in src
        assert "NULLIF(TRIM(p.default_code), '')" in src
        assert r"REGEXP_EXTRACT(ad.name, r'\[([A-Z][A-Z0-9._-]*)\]')" in src

    def test_150_preserves_existing_consumer_columns(self):
        src = _sql_source()
        for col in (
            "product_id",
            "producto",
            "referencia_interna",
            "producto_con_referencia",
            "balance_asignado",
            "empresa_nombre",
            "cc_nombre",
            "cc_codigo",
            "cc_activo",
            "distribucion_resuelta",
        ):
            assert col in src, f"View must keep existing column {col}"

    def test_150_sql_still_creates_view(self):
        src = _sql_source()
        assert "CREATE OR REPLACE VIEW" in src
        assert (
            "`ace-scarab-484515-v1.odoo_data.vw_apuntes_analiticos_desglosados`" in src
        )
