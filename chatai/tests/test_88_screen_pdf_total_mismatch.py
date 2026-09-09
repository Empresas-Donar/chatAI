"""
Regression tests for issue #88: the on-screen total ("Total a Pagar") for the
Orden de Compra / Orden de Facturación reports did not match the total shown
in the downloaded PDF, for the same contratista/empresa/date range.

Root cause: get_purchase_order (GET /api/purchase-orders, used by both
purchase_orders.js and billing_order.js to render the on-screen header total)
computed total_al_dia with an EXACT match against tipo_pago == "Al dia".
Any row whose tipo_pago was neither exactly "trato" nor exactly "Al dia"
(e.g. "Bono") was silently dropped from both total_al_dia and the grand
total shown on screen.

Both PDF endpoints in the same file — purchase_order_print_pdf
(/api/purchase-orders/print-pdf) and billing_order_pdf
(/api/odoo/facturacion/pdf) — already computed total_al_dia as a catch-all
("everything that isn't trato"), so their total always equalled the full
SUM(total_labor) and never dropped rows.

Fix: get_purchase_order now uses the same catch-all pattern
(tipo_pago != _PAYMENT_TYPE_TRATO) as the two PDF endpoints, so screen and
PDF totals can no longer drift apart.
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
import tarjas_empresa as te

# Real reported case (issue #88): as of writing, tarjas_reporte has
#   tipo_pago='Al dia' -> 50 rows / $4,780,200
#   tipo_pago='Bono'   ->  2 rows / $103,643   (dropped by the pre-fix bug)
#   tipo_pago='trato'  ->  7 rows / $3,233,983
# full total = 8,117,826 ; pre-fix (buggy) screen total = 8,014,183
CONTRATISTA = "MULTISERVICIOS BONHOMIA SPA"
EMPRESA = "ZUÑIGA"
FECHA_INICIO = "2026-07-29"
FECHA_TERMINO = "2026-08-04"


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


def _full_sum_costo_empresa(conn, contratista, empresa, fecha_inicio, fecha_termino):
    """Ground truth: Costo Empresa from every Aprobado row, all tipo_pago.

    Screen and PDF must both equal this — including Bono (factor 1.0), which
    the pre-#88 exact-match on 'Al dia' used to drop.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tipo_pago, COALESCE(SUM(total_trabajado), 0)
            FROM appsheet.tarjas_pagos
            WHERE estado = 'Aprobado'
              AND contratista = %s AND nombre_campo = %s
              AND fecha::date BETWEEN %s AND %s
            GROUP BY tipo_pago, cuartel_cc, labor
            """,
            (contratista, empresa, fecha_inicio, fecha_termino),
        )
        return sum(float(te.total_empresa(tipo, amt)) for tipo, amt in cur.fetchall())


class TestScreenTotalMatchesFullSum:
    def test_88_screen_pdf_total_mismatch_regression(self, conn):
        """The on-screen header total must equal Costo Empresa across every
        tipo_pago — it must not silently drop rows whose tipo_pago is
        neither 'trato' nor exactly 'Al dia' (e.g. 'Bono')."""
        expected_full_total = _full_sum_costo_empresa(
            conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
        )
        assert expected_full_total > 0, "expected data for this known dataset"

        result = run(
            poc.get_purchase_order(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        header = result["header"]
        assert header is not None

        assert header["total"] == pytest.approx(expected_full_total, abs=0.01)
        assert header["total_trato"] + header["total_al_dia"] == pytest.approx(
            expected_full_total, abs=0.01
        )

    def test_88_screen_total_matches_print_pdf_total_source_regression(self, conn):
        """Screen (get_purchase_order) and 'Orden de Compra' PDF
        (purchase_order_print_pdf) must derive the exact same grand total
        from the same underlying rows — this is the bug from #88."""
        screen = run(
            poc.get_purchase_order(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        screen_total = screen["header"]["total"]

        with conn.cursor() as cur:
            pdf_rows = poc._purchase_order_lines(
                cur, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
            )
        pdf_header = poc._purchase_order_header(
            pdf_rows, FECHA_INICIO, FECHA_TERMINO
        )
        assert screen_total == pytest.approx(pdf_header["total"], abs=0.01)
        src = __import__("inspect").getsource(poc.purchase_order_print_pdf)
        assert "_purchase_order_lines" in src

    def test_88_print_pdf_still_renders(self):
        """purchase_order_print_pdf (unchanged by this fix) must keep working."""
        resp = run(
            poc.purchase_order_print_pdf(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        body = run(_pdf_bytes(resp))
        assert body[:4] == b"%PDF"

    def test_88_billing_order_pdf_still_renders(self):
        """billing_order_pdf (unchanged by this fix) must keep working."""
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
    def test_88_purchase_order_scoped_to_contratista_and_empresa_isolation(self, conn):
        """A contractor/company pair with no rows in the given range must not
        pick up another contractor's or another farm's totals (tenant/farm
        scoping via WHERE contratista = %s AND nombre_campo = %s)."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT contratista FROM appsheet.tarjas_reporte
                WHERE contratista != %s AND fecha BETWEEN %s AND %s
                LIMIT 1
                """,
                (CONTRATISTA, FECHA_INICIO, FECHA_TERMINO),
            )
            row = cur.fetchone()
        assert row is not None, (
            "expected at least one other contratista to compare against"
        )
        other_contratista = row[0]

        result_a = run(
            poc.get_purchase_order(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        result_b = run(
            poc.get_purchase_order(
                contratista=other_contratista,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )

        rows_a = {(r["contratista"], r["nombre_campo"]) for r in result_a["rows"]}
        rows_b = {(r["contratista"], r["nombre_campo"]) for r in result_b["rows"]}
        assert rows_a.isdisjoint(rows_b), (
            "rows for one contratista leaked into another contratista's result"
        )
        for c, _e in rows_a:
            assert c == CONTRATISTA
        for c, _e in rows_b:
            assert c == other_contratista


def test_purchase_order_js_computes_pct_from_total_labor():
    from pathlib import Path

    js = (
        Path(__file__).parent.parent
        / "frontend"
        / "static"
        / "purchase_orders.js"
    ).read_text(encoding="utf-8")
    render_src = js.split("function renderDocument")[1].split("function renderChart")[0]
    assert "total_labor" in render_src
    assert "grand > 0" in render_src
    assert "row['% Tipo de pago']" not in render_src


class TestPurchaseOrderPctDelTotal:
    def test_pct_pago_is_share_of_grand_total(self, conn):
        result = run(
            poc.get_purchase_order(
                contratista="MULTISERVICIOS BONHOMIA SPA",
                empresa="ZUÑIGA",
                fecha_inicio="2026-09-02",
                fecha_termino="2026-09-08",
            )
        )
        rows = result["rows"]
        assert rows
        grand = sum(float(r["total_labor"] or 0) for r in rows)
        assert grand > 0
        for r in rows:
            expected = round(float(r["total_labor"] or 0) / grand * 100, 2)
            assert abs(float(r["pct_pago"] or 0) - expected) < 0.02
        assert abs(sum(float(r["pct_pago"] or 0) for r in rows) - 100.0) < 0.15
        import inspect

        src = inspect.getsource(poc._purchase_order_lines)
        assert "PARTITION BY tipo_pago" not in src
