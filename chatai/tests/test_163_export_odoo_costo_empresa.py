"""
test_163_export_odoo_costo_empresa.py
--------------------------------------
Regression test for issue #163: tarjas_reporte_odoo used pagar_efectivo
(total_trabajado + total_contratista) as order_line/price_unit, producing
export totals that differed from the Orden de Compra header by ~$65.290.

Fix: the SQL view now exposes total_unitario_empresa = AVG(total_trabajado ×
factor) where factor = 1.50 para trato, 1.45 al día, 1.0 para el resto.
The view uses total_unitario_empresa as price_unit so the export total cuadra
with the OC Costo Empresa total.

Invariant under test:
    SUM("order_line/product_qty" * "order_line/price_unit")  (tarjas_reporte_odoo)
    ≈
    SUM(total_trabajado * factor)  (tarjas_pagos, mismo filtro)

Tolerance: 1 CLP (AVG vs SUM rounding across jornadas of the same partition).

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_163_export_odoo_costo_empresa.py -v
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

from db import get_connection  # noqa: E402
from tarjas_empresa import total_empresa  # noqa: E402

# Concrete case from the original bug report (a week with the $65.290 delta)
CONTRATISTA = "MULTISERVICIOS BONHOMIA SPA"
NOMBRE_CAMPO = "ZUÑIGA"
FECHA_INICIO = "2026-08-12"
FECHA_TERMINO = "2026-08-18"

# Tolerance in CLP: averaging within partitions can cause <1 CLP rounding vs
# summing per-row. We allow up to 1 CLP per exported line (generous upper bound).
TOLERANCE_PER_LINE = 1.0


@pytest.fixture(scope="module")
def db():
    conn = get_connection()
    yield conn
    conn.close()


class TestIssue163ExportCostoEmpresa:
    """Regression suite: tarjas_reporte_odoo price_unit = Costo Empresa, not pagar_efectivo."""

    def test_163_view_uses_total_unitario_empresa(self):
        """
        Source SQL must reference total_unitario_empresa (not total_unitario)
        as order_line/price_unit in tarjas_reporte_odoo.
        """
        sql_file = (
            Path(__file__).parent.parent.parent / "sql" / "tarjas" / "02_views_odoo.sql"
        )
        src = sql_file.read_text(encoding="utf-8")
        # Ensure total_unitario_empresa appears as price_unit, not the old total_unitario
        assert "total_unitario_empresa" in src, (
            "02_views_odoo.sql must reference total_unitario_empresa for order_line/price_unit"
        )
        # The bare "total_unitario" (without "_empresa") must no longer appear as
        # price_unit. We check both aliased columns in the view SELECT.
        lines_with_price_unit = [
            line
            for line in src.splitlines()
            if "price_unit" in line.lower() and "price_un" in line.lower()
        ]
        for line in lines_with_price_unit:
            # Strip comments
            code = line.split("--")[0]
            assert "total_unitario_empresa" in code or "total_unitario" not in code, (
                f"price_unit line still references bare total_unitario: {line.strip()}"
            )

    def test_163_tarjas_reporte_has_total_unitario_empresa_column(self, db):
        """
        tarjas_reporte must expose the new total_unitario_empresa column.
        """
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'appsheet'
                  AND table_name   = 'tarjas_reporte'
                  AND column_name  = 'total_unitario_empresa'
                """
            )
            row = cur.fetchone()
        assert row is not None, (
            "tarjas_reporte view must have column 'total_unitario_empresa' (issue #163)"
        )

    def test_163_export_odoo_costo_empresa_regression(self, db):
        """
        Regression: SUM(qty * price_unit) in tarjas_reporte_odoo must match
        SUM(total_trabajado * factor) computed directly from tarjas_pagos.

        Before the fix both used pagar_efectivo; the OC used Costo Empresa.
        That delta ($65.290 in the bug report) must now be zero (within rounding).
        """
        with db.cursor() as cur:
            # Export total: what goes into the xlsx
            cur.execute(
                """
                SELECT COALESCE(SUM("order_line/product_qty" * "order_line/price_unit"), 0)
                FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor"  = %s
                  AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            (export_total,) = cur.fetchone()

            # OC total: same formula as _purchase_order_lines in the controller
            cur.execute(
                """
                SELECT tipo_pago, SUM(COALESCE(total_trabajado, 0)) AS trab
                FROM appsheet.tarjas_pagos
                WHERE estado = 'Aprobado'
                  AND contratista  = %s
                  AND nombre_campo = %s
                  AND fecha::date BETWEEN %s AND %s
                GROUP BY tipo_pago
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            oc_total = sum(
                float(total_empresa(tipo, trab)) for tipo, trab in cur.fetchall()
            )

        assert export_total is not None, "export_total should not be None"

        export_f = float(export_total)
        delta = abs(export_f - oc_total)

        # Fetch row count for per-line tolerance
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor"  = %s
                  AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            (row_count,) = cur.fetchone()

        tolerance = max(TOLERANCE_PER_LINE * (row_count or 1), 1.0)
        assert delta <= tolerance, (
            f"Export total ({export_f:,.0f} CLP) differs from OC Costo Empresa "
            f"({oc_total:,.0f} CLP) by {delta:,.0f} CLP — exceeds tolerance {tolerance:.0f}. "
            "price_unit must be total_unitario_empresa, not pagar_efectivo (issue #163)."
        )

    def test_163_total_unitario_empresa_less_than_or_equal_total_unitario(self, db):
        """
        Sanity check: total_unitario_empresa (Costo Empresa) should always be <=
        total_unitario (pagar_efectivo) for 'al dia' and 'trato' rows, since
        pagar_efectivo adds the contratista margin on top of total_trabajado.
        Any row where empresa > efectivo indicates a data anomaly.
        """
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM appsheet.tarjas_reporte
                WHERE contratista  = %s
                  AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                  AND LOWER(tipo_pago) IN ('al dia', 'al día', 'trato')
                  AND total_unitario_empresa > total_unitario + 1
                """,
                (CONTRATISTA, NOMBRE_CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            (anomalies,) = cur.fetchone()
        assert anomalies == 0, (
            f"{anomalies} rows where total_unitario_empresa > total_unitario for "
            "al dia/trato — check that Costo Empresa formula is correct (issue #163)"
        )
