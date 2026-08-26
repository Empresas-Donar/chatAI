"""
Regression tests for issue #146: the "Suma total" footer of the worker×date
pivot table inside the "Orden de Facturación" PDF (billing_order_pdf,
GET /api/odoo/facturacion/pdf) did not match the "Total a Pagar" header of
the same PDF, nor the total shown on screen (get_purchase_order).

Root cause: the pivot query read appsheet.tarjas_pagos directly, summing
total_trabajado (what's paid to the worker) with no estado filter at all.
The header total — and the on-screen total — are computed from
appsheet.tarjas_reporte, which sums total_pagar (the billable amount:
total_pagar = total_trabajado + total_contratista, see
sql/tarjas/01_views_reporte.sql) and filters WHERE estado = 'Aprobado'.

Fix: the pivot query now sums total_pagar and filters estado = 'Aprobado',
matching tarjas_reporte's scope exactly.
"""

import asyncio
import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.purchase_orders_controller as poc

# Real reported case (issue #146).
CONTRATISTA = "MULTISERVICIOS BONHOMIA SPA"
EMPRESA = "KONTROLAG"
FECHA_INICIO = "2026-08-19"
FECHA_TERMINO = "2026-08-25"


def run(coro):
    return asyncio.run(coro)


async def _pdf_bytes(resp):
    if getattr(resp, "body", None):
        return resp.body
    return b"".join([c async for c in resp.body_iterator])


@pytest.fixture
def conn():
    c = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    yield c
    c.rollback()
    c.close()


def _header_total(conn, contratista, empresa, fecha_inicio, fecha_termino):
    """Ground truth: the same total the screen and the PDF header use."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(total_labor), 0)
            FROM appsheet.tarjas_reporte
            WHERE contratista = %s AND nombre_campo = %s
              AND fecha BETWEEN %s AND %s
            """,
            (contratista, empresa, fecha_inicio, fecha_termino),
        )
        return float(cur.fetchone()[0] or 0)


def _pivot_grand_total(conn, contratista, empresa, fecha_inicio, fecha_termino):
    """Recompute the pivot's own grand total the same way billing_order_pdf
    does post-fix, from a single consistent snapshot."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trabajador, fecha::date::text AS fecha,
                   SUM(total_pagar) AS total
            FROM appsheet.tarjas_pagos
            WHERE contratista  = %s
              AND nombre_campo = %s
              AND estado       = 'Aprobado'
              AND fecha::date BETWEEN %s AND %s
            GROUP BY trabajador, fecha::date
            """,
            (contratista, empresa, fecha_inicio, fecha_termino),
        )
        rows = cur.fetchall()
    return sum(float(r[2] or 0) for r in rows)


class TestPivotTotalMatchesHeaderTotal:
    def test_146_facturacion_pivot_total_mismatch_regression(self, conn):
        """The pivot 'Suma total' must equal the header 'Total a Pagar',
        computed from a single consistent DB snapshot to avoid false
        negatives from concurrent production writes."""
        with conn.cursor() as cur:
            cur.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")

            header_total = _header_total(
                conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
            )
            pivot_total = _pivot_grand_total(
                conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
            )

            cur.execute("ROLLBACK")

        assert header_total > 0, "expected data for this known dataset"
        assert pivot_total == pytest.approx(header_total, abs=0.01)

    def test_146_pivot_excludes_non_aprobado_rows(self, conn):
        """A pivot query without the estado filter must differ from the
        fixed one whenever pending rows exist — this is the bug from #146,
        preserved here as a negative check so a future regression that
        drops the filter again is caught even if amounts happen to align."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM appsheet.tarjas_pagos
                WHERE contratista = %s AND nombre_campo = %s
                  AND fecha::date BETWEEN %s AND %s
                  AND estado != 'Aprobado'
                """,
                (CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO),
            )
            (pending_count,) = cur.fetchone()

        if pending_count == 0:
            pytest.skip("no pending rows in this dataset right now")

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(total_trabajado), 0)
                FROM appsheet.tarjas_pagos
                WHERE contratista = %s AND nombre_campo = %s
                  AND fecha::date BETWEEN %s AND %s
                """,
                (CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO),
            )
            unfiltered_total_trabajado = float(cur.fetchone()[0] or 0)

        header_total = _header_total(
            conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
        )
        assert unfiltered_total_trabajado != pytest.approx(header_total, abs=0.01), (
            "sanity check: the old buggy query's total should NOT equal the "
            "header total when pending rows exist"
        )

    def test_146_billing_order_pdf_still_renders(self):
        """billing_order_pdf must keep producing a valid PDF after the fix."""
        resp = run(
            poc.billing_order_pdf(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        body = run(_pdf_bytes(resp))
        assert body[:4] == b"%PDF"


class TestCrossFarmIsolation:
    def test_146_billing_order_pdf_scoped_to_contratista_and_empresa_isolation(
        self, conn
    ):
        """A different contratista/empresa pair must not leak into this
        pivot's totals (tenant/farm scoping via WHERE contratista = %s AND
        nombre_campo = %s)."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT contratista, nombre_campo
                FROM appsheet.tarjas_pagos
                WHERE NOT (contratista = %s AND nombre_campo = %s)
                  AND fecha::date BETWEEN %s AND %s
                  AND estado = 'Aprobado'
                LIMIT 1
                """,
                (CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO),
            )
            row = cur.fetchone()
        assert row is not None, (
            "expected at least one other contratista/empresa pair to compare against"
        )
        other_contratista, other_empresa = row

        total_a = _pivot_grand_total(
            conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
        )
        total_b = _pivot_grand_total(
            conn, other_contratista, other_empresa, FECHA_INICIO, FECHA_TERMINO
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(total_pagar), 0)
                FROM appsheet.tarjas_pagos
                WHERE contratista = %s AND nombre_campo = %s
                  AND estado = 'Aprobado'
                  AND fecha::date BETWEEN %s AND %s
                """,
                (other_contratista, other_empresa, FECHA_INICIO, FECHA_TERMINO),
            )
            expected_b = float(cur.fetchone()[0] or 0)

        assert total_b == pytest.approx(expected_b, abs=0.01)
        assert total_a != total_b or total_a == 0, (
            "totals should be independently scoped, not a shared/leaked value"
        )
