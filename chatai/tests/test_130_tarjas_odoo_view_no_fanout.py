"""
test_130_tarjas_odoo_view_no_fanout.py
---------------------------------------
Regression test for issue #130: appsheet.tarjas_reporte_odoo was silently
duplicating jornadas/amounts for any labor whose id_labor (or normalized text,
or [X.Y]/X.Y- prefix) matched more than one row in appsheet.tarjas_labores.

appsheet.tarjas_labores has no uniqueness constraint on id_labor, and several
labors legitimately share a codigo_labor across text/punctuation variants
(e.g. issues #32, #124). The l0-l3 LEFT JOINs in
sql/tarjas/02_views_odoo.sql used to join against tarjas_labores directly, so
a labor with 2 matching catalog rows produced 2 output rows in
tarjas_reporte_odoo for the same real-world jornada — doubling the amount
that gets exported/imported into Odoo, even though both matches resolved to
the identical codigo_labor.

Concretely: id_labor='8.1' had two catalog rows ("ASEO Y ORNATO" and "TALLER
Y BODEGA"). Every "ASEO Y ORNATO" jornada for MULTISERVICIOS BONHOMIA SPA /
ZUÑIGA and SERVICIOS AGRICOLAS GUTIERREZ II SPA / ZUÑIGA (2026-08-12 to
2026-08-18) was exported twice, inflating the Excel total by $496,500 and
$150,000 respectively versus what the on-screen "visor" (GET
/api/purchase-orders, which reads tarjas_reporte directly) showed.

Fix: each l0-l3 join in the view is now `LEFT JOIN LATERAL (... LIMIT 1)`,
guaranteeing at most one matching row per labor regardless of how many
duplicate catalog rows exist.

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_130_tarjas_odoo_view_no_fanout.py -v
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

_db_url = os.environ.get("DATABASE_URL", "")
if _db_url and not os.environ.get("DB_HOST"):
    from urllib.parse import unquote, urlparse

    _u = urlparse(_db_url)
    os.environ["DB_USER"] = unquote(_u.username or "")
    os.environ["DB_PASSWORD"] = unquote(_u.password or "")
    os.environ["DB_HOST"] = _u.hostname or ""
    os.environ["DB_PORT"] = str(_u.port or 5432)
    os.environ["DB_NAME"] = _u.path.lstrip("/")

from db import get_connection

# Real case that surfaced the bug (issue #130), used as a concrete regression
# fixture — kept narrow (one contractor/campo/date range) rather than
# asserting over the whole table, to stay fast and stable over time.
CONTRATISTA = "MULTISERVICIOS BONHOMIA SPA"
NOMBRE_CAMPO = "ZUÑIGA"
FECHA_INICIO = "2026-08-12"
FECHA_TERMINO = "2026-08-18"


@pytest.fixture(scope="module")
def db():
    conn = get_connection()
    yield conn
    conn.close()


class TestIssue130NoFanoutRegression:
    """Regression suite: tarjas_reporte_odoo must never multiply rows via l0-l3 joins."""

    def test_130_view_uses_lateral_limit_1_joins(self):
        """
        Regression: the view source must use LATERAL ... LIMIT 1 for every
        tarjas_labores join, not a plain LEFT JOIN — a plain join re-introduces
        the fan-out bug the moment tarjas_labores gets a second row sharing an
        id_labor, normalized text, or [X.Y]/X.Y- prefix.
        """
        sql_file = (
            Path(__file__).parent.parent.parent / "sql" / "tarjas" / "02_views_odoo.sql"
        )
        src = sql_file.read_text(encoding="utf-8")
        lateral_count = src.count("LEFT JOIN LATERAL")
        assert lateral_count == 4, (
            f"Expected 4 LATERAL joins (l0-l3 against tarjas_labores), found {lateral_count}"
        )
        for alias in ("l0", "l1", "l2", "l3"):
            assert f") {alias} ON" in src, (
                f"Join {alias} must be a LATERAL subquery with LIMIT 1, not a plain join"
            )

    def test_130_catalog_still_has_duplicate_id_labor(self, db):
        """
        Sanity check that the scenario this bug depends on still exists in
        production: tarjas_labores has rows sharing id_labor='8.1'
        ("ASEO Y ORNATO" / "TALLER Y BODEGA"). If this ever stops being true
        (catalog cleaned up), the regression below is still valid — LIMIT 1
        protects against any future duplicate, not just this specific pair.
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM appsheet.tarjas_labores WHERE id_labor = '8.1'"
            )
            (count,) = cur.fetchone()
        assert count >= 2, (
            "Expected the known duplicate id_labor='8.1' catalog rows to still "
            "be present — if this fails because they were cleaned up, that's "
            "fine, but double check the LATERAL LIMIT 1 fix separately."
        )

    def test_130_odoo_view_row_count_matches_reporte_regression(self, db):
        """
        Regression: for the exact case that surfaced the bug, tarjas_reporte_odoo
        must have the same row count as tarjas_reporte (one row per labor/día/CC/
        tipo_pago) — no fan-out from the tarjas_labores joins.
        """
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM appsheet.tarjas_reporte
                WHERE contratista = %s AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            (reporte_count,) = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*) FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor" = %s AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            (odoo_count,) = cur.fetchone()

        assert odoo_count == reporte_count, (
            f"tarjas_reporte_odoo has {odoo_count} rows but tarjas_reporte has "
            f"{reporte_count} for the same filter — a join is fanning out rows "
            "again (issue #130 regression)"
        )

    def test_130_aseo_y_ornato_not_duplicated_regression(self, db):
        """
        Regression: the exact duplicated labor from the bug report — "ASEO Y
        ORNATO" for BONHOMIA/ZUÑIGA — must appear exactly once per (fecha,
        tipo_pago, CC) in the Odoo export view, not twice.
        """
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT fecha, tipo_pago,
                       "Lineas del pedido/Código de Distribución Analítica/Código",
                       COUNT(*)
                FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor" = %s AND nombre_campo = %s
                  AND "Lineas del pedido/Producto/Nombre" = 'ASEO Y ORNATO'
                  AND fecha BETWEEN %s AND %s
                GROUP BY 1, 2, 3
                HAVING COUNT(*) > 1
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            duplicates = cur.fetchall()
        assert duplicates == [], (
            f"'ASEO Y ORNATO' still duplicated in tarjas_reporte_odoo: {duplicates}"
        )

    def test_130_visor_and_excel_totals_match_within_rounding(self, db):
        """
        Regression: the on-screen total (tarjas_reporte, what GET
        /api/purchase-orders shows) and the Odoo export total
        (tarjas_reporte_odoo, what gets downloaded/imported) must match to
        within a few cents of rounding — not off by hundreds of thousands of
        pesos from a doubled labor.
        """
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT SUM(total_labor) FROM appsheet.tarjas_reporte
                WHERE contratista = %s AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            (visor_total,) = cur.fetchone()

            cur.execute(
                """
                SELECT SUM("order_line/product_qty" * "order_line/price_unit")
                FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor" = %s AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            (excel_total,) = cur.fetchone()

        assert visor_total is not None and excel_total is not None
        assert abs(float(visor_total) - float(excel_total)) < 1.0, (
            f"visor total ({visor_total}) and Excel export total ({excel_total}) "
            "differ by more than rounding — a join is duplicating rows again"
        )
