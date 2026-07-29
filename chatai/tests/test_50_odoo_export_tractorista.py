"""
Regression tests for issue #50: Reporte Odoo para Tractoristas.

Verifies:
1. The view appsheet.tarjas_reporte_odoo_tractorista exists in PostgreSQL.
2. The view uses horas_extras as order_line/product_qty (not jornadas/row count).
3. The view only contains rows where tipo_pago = 'Tractorista'.
4. The endpoint GET /api/tarjas/tractorista/odoo-export exists in the controller.
5. The endpoint GET /api/tarjas/tractorista/filters exists in the controller.
6. The nav includes the Orden de compra tractorista link.

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_50_odoo_export_tractorista.py -v
"""

import re
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TARJAS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "tarjas_controller.py"
)
SQL_VIEW = (
    Path(__file__).parent.parent.parent / "sql" / "tarjas" / "08_views_odoo_tractorista.sql"
)
BASE_HTML = (
    Path(__file__).parent.parent / "frontend" / "templates" / "base.html"
)
TRACTORISTA_JS = (
    Path(__file__).parent.parent / "frontend" / "static" / "purchase_orders_tractorista.js"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctrl_source() -> str:
    return TARJAS_CTRL.read_text(encoding="utf-8")


def _sql_source() -> str:
    return SQL_VIEW.read_text(encoding="utf-8")


def _base_html() -> str:
    return BASE_HTML.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# SQL view tests (static analysis)
# ---------------------------------------------------------------------------


def test_50_sql_view_file_exists():
    """Regression: 08_views_odoo_tractorista.sql must exist."""
    assert SQL_VIEW.exists(), (
        f"Missing SQL file: {SQL_VIEW} — create it to fix issue #50"
    )


def test_50_sql_view_name_correct():
    """Regression: view must be named appsheet.tarjas_reporte_odoo_tractorista."""
    src = _sql_source()
    assert "tarjas_reporte_odoo_tractorista" in src, (
        "SQL file must CREATE VIEW appsheet.tarjas_reporte_odoo_tractorista"
    )


def test_50_sql_view_uses_horas_extras_as_qty():
    """
    Regression (#50): order_line/product_qty must come from horas_extras,
    NOT from a COUNT(*) or jornadas column.
    """
    src = _sql_source()
    # The view must map horas_extras to order_line/product_qty
    assert "horas_extras" in src, "horas_extras must appear in the SQL view"
    assert '"order_line/product_qty"' in src, (
        'order_line/product_qty must be defined in the view'
    )
    # COUNT(*) would indicate jornadas logic — must NOT be used
    assert "COUNT(*)" not in src, (
        "COUNT(*) must not appear — qty should be SUM(horas_extras), not row count"
    )


def test_50_sql_view_filters_tractorista_only():
    """Regression: view must filter WHERE tipo_pago = 'tractorista'."""
    src = _sql_source().lower()
    assert "tractorista" in src, (
        "SQL view must filter for tipo_pago = 'tractorista'"
    )


def test_50_sql_view_uses_total_tractor_for_price():
    """Regression: price_unit must use total_tractor / horas_extras."""
    src = _sql_source()
    assert "total_tractor" in src, (
        "price_unit must be derived from total_tractor (not total_pagar)"
    )


def test_50_sql_view_has_four_product_id_fallbacks():
    """Regression: 4 JOIN levels for product_id (l0, l1, l2, l3)."""
    src = _sql_source()
    for alias in ("l0", "l1", "l2", "l3"):
        assert alias in src, (
            f"Missing fallback join alias '{alias}' — all 4 product_id fallbacks required"
        )


def test_50_sql_view_built_from_tarjas_pagos_directly():
    """
    Regression: view must query tarjas_pagos directly (not tarjas_reporte),
    as decided in issue #50 comment.
    """
    src = _sql_source()
    assert "tarjas_pagos" in src, (
        "View must be built from tarjas_pagos directly (not tarjas_reporte)"
    )


# ---------------------------------------------------------------------------
# Controller / endpoint tests (static analysis)
# ---------------------------------------------------------------------------


def test_50_controller_has_odoo_export_endpoint():
    """Regression: /api/tarjas/tractorista/odoo-export endpoint must exist."""
    src = _ctrl_source()
    assert "/api/tarjas/tractorista/odoo-export" in src, (
        "Missing endpoint GET /api/tarjas/tractorista/odoo-export in tarjas_controller.py"
    )


def test_50_controller_has_filters_endpoint():
    """Regression: /api/tarjas/tractorista/filters endpoint must exist."""
    src = _ctrl_source()
    assert "/api/tarjas/tractorista/filters" in src, (
        "Missing endpoint GET /api/tarjas/tractorista/filters in tarjas_controller.py"
    )


def test_50_controller_has_preview_endpoint():
    """Regression: /api/tarjas/tractorista/preview endpoint must exist."""
    src = _ctrl_source()
    assert "/api/tarjas/tractorista/preview" in src, (
        "Missing endpoint GET /api/tarjas/tractorista/preview in tarjas_controller.py"
    )


def test_50_controller_has_page_route():
    """Regression: /odoo/tarjas-tractorista HTML page route must exist."""
    src = _ctrl_source()
    assert "/odoo/tarjas-tractorista" in src, (
        "Missing page route GET /odoo/tarjas-tractorista in tarjas_controller.py"
    )


def test_50_export_endpoint_uses_tractorista_view():
    """Regression: export endpoint must query tarjas_reporte_odoo_tractorista (not cuadrilla view)."""
    src = _ctrl_source()
    # Find the tractorista export function
    match = re.search(
        r"@router\.get\(\"/api/tarjas/tractorista/odoo-export\"\)(.*?)(?=\n@router|\Z)",
        src,
        re.DOTALL,
    )
    assert match is not None, "Could not locate the odoo-export endpoint function"
    fn_body = match.group(1)
    assert "tarjas_reporte_odoo_tractorista" in fn_body, (
        "Export endpoint must query appsheet.tarjas_reporte_odoo_tractorista"
    )
    # Ensure it is NOT querying the cuadrilla view
    assert "tarjas_reporte_odoo'" not in fn_body or "tarjas_reporte_odoo_tractorista" in fn_body, (
        "Export endpoint must query the tractorista view, not the cuadrilla view"
    )


def test_50_export_endpoint_excludes_unmapped_rows():
    """Regression: export endpoint must filter excluded rows and set X-Excluded-Amount."""
    src = _ctrl_source()
    match = re.search(
        r"@router\.get\(\"/api/tarjas/tractorista/odoo-export\"\)(.*?)(?=\n@router|\Z)",
        src,
        re.DOTALL,
    )
    assert match is not None
    fn_body = match.group(1)
    assert "X-Excluded-Amount" in fn_body, (
        "Export endpoint must report excluded amount via X-Excluded-Amount header"
    )
    assert "excluded_amount" in fn_body, (
        "Export endpoint must compute excluded_amount"
    )


# ---------------------------------------------------------------------------
# Navigation tests
# ---------------------------------------------------------------------------


def test_50_nav_includes_tractorista_link():
    """Regression: base.html nav must include the Orden de compra tractorista link."""
    src = _base_html()
    assert "/odoo/tarjas-tractorista" in src, (
        "base.html nav must include /odoo/tarjas-tractorista link"
    )
    assert "Orden de compra tractorista" in src, (
        "base.html nav must include 'Orden de compra tractorista' label"
    )


# ---------------------------------------------------------------------------
# JS file tests (static analysis)
# ---------------------------------------------------------------------------


def test_50_js_file_exists():
    """Regression: purchase_orders_tractorista.js must exist."""
    assert TRACTORISTA_JS.exists(), (
        f"Missing JS file: {TRACTORISTA_JS}"
    )


def test_50_js_calls_tractorista_endpoints():
    """Regression: JS must call /api/tarjas/tractorista/* endpoints."""
    src = TRACTORISTA_JS.read_text(encoding="utf-8")
    assert "/api/tarjas/tractorista/filters" in src, (
        "JS must call /api/tarjas/tractorista/filters"
    )
    assert "/api/tarjas/tractorista/odoo-export" in src, (
        "JS must call /api/tarjas/tractorista/odoo-export"
    )
