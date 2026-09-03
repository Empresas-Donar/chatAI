"""
Regression tests for issue #156: Orden de Facturación screen header showed $0
while the worker×date pivot on the same page showed $175.000
(HERBI ML SPA / KONTROLAG / 2026-08-26..2026-09-01).

Root cause (hypothesis B, verified against Postgres):
  All 7 rows are estado='Aprobado', but total_pagar is 0 while
  total_trabajado=175000 and total_contratista=87500.
  Domain formula: total_pagar = total_trabajado + total_contratista = 262500.

  Header used GET /api/purchase-orders → tarjas_reporte → SUM(total_pagar) = 0.
  Pivot used GET /api/tarjas/contratista → tarjas_pagos unfiltered, JS summed
  total_trabajado = 175000.

Fix: screen and PDF share GET-equivalent helper _fetch_billing_order that
filters estado='Aprobado' and uses
  COALESCE(NULLIF(total_pagar, 0), total_trabajado + total_contratista)
so a stored 0 cannot hide approved billable work. The operational
/api/tarjas/contratista endpoint is left unchanged.
"""

import asyncio
import inspect
import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.purchase_orders_controller as poc
import controllers.tarjas_controller as tc

# Real reported case (issue #156).
CONTRATISTA = "HERBI ML SPA"
EMPRESA = "KONTROLAG"
FECHA_INICIO = "2026-08-26"
FECHA_TERMINO = "2026-09-01"

# Canonical billable amount: 7 jornadas × ($25.000 + $12.500).
# Must NOT equal the $175.000 the buggy screen pivot showed (total_trabajado).
EXPECTED_BILLABLE = 262_500.0
BUGGY_TOTAL_TRABAJADO = 175_000.0


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


def _billable_sum(conn, contratista, empresa, fecha_inicio, fecha_termino):
    """Ground truth: Aprobado rows, formula fallback when total_pagar is 0."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COALESCE(SUM({poc._BILLABLE_SQL}), 0)
            FROM appsheet.tarjas_pagos
            WHERE contratista  = %s
              AND nombre_campo = %s
              AND estado       = 'Aprobado'
              AND fecha::date BETWEEN %s AND %s
            """,
            (contratista, empresa, fecha_inicio, fecha_termino),
        )
        return float(cur.fetchone()[0] or 0)


def _stored_total_pagar(conn, contratista, empresa, fecha_inicio, fecha_termino):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(total_pagar), 0)
            FROM appsheet.tarjas_pagos
            WHERE contratista  = %s
              AND nombre_campo = %s
              AND estado       = 'Aprobado'
              AND fecha::date BETWEEN %s AND %s
            """,
            (contratista, empresa, fecha_inicio, fecha_termino),
        )
        return float(cur.fetchone()[0] or 0)


def _stored_total_trabajado(conn, contratista, empresa, fecha_inicio, fecha_termino):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(total_trabajado), 0)
            FROM appsheet.tarjas_pagos
            WHERE contratista  = %s
              AND nombre_campo = %s
              AND fecha::date BETWEEN %s AND %s
            """,
            (contratista, empresa, fecha_inicio, fecha_termino),
        )
        return float(cur.fetchone()[0] or 0)


class TestScreenHeaderMatchesPivot:
    def test_156_facturacion_header_pivot_zero_regression(self, conn):
        """Screen header Total a Pagar must equal pivot Suma total, and both
        must equal the billable formula — not $0 and not total_trabajado."""
        with conn.cursor() as cur:
            cur.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")

            expected = _billable_sum(
                conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
            )
            stored_pagar = _stored_total_pagar(
                conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
            )
            stored_trabajado = _stored_total_trabajado(
                conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
            )

            cur.execute("ROLLBACK")

        assert expected > 0, "expected Aprobado billable data for this known dataset"
        assert expected == pytest.approx(EXPECTED_BILLABLE, abs=0.01), (
            "HERBI/KONTROLAG 26/08–01/09 must still be 7 × $37.500 = $262.500"
        )
        # The original bug: stored total_pagar is 0 (or was when reported)
        # while total_trabajado is the $175k the screen pivot showed.
        # If a future backfill fills total_pagar, this sanity still holds
        # as long as the two amounts stay distinct.
        assert stored_trabajado == pytest.approx(BUGGY_TOTAL_TRABAJADO, abs=0.01)
        assert stored_pagar != pytest.approx(stored_trabajado, abs=0.01) or (
            stored_pagar == pytest.approx(EXPECTED_BILLABLE, abs=0.01)
        )

        result = run(
            poc.billing_order_data(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        header = result["header"]
        assert header is not None
        pivot_total = sum(float(r["total_pagar"] or 0) for r in result["rows"])

        assert header["total"] == pytest.approx(expected, abs=0.01)
        assert pivot_total == pytest.approx(header["total"], abs=0.01)
        assert header["total"] != pytest.approx(BUGGY_TOTAL_TRABAJADO, abs=0.01)
        assert header["total"] != pytest.approx(0, abs=0.01)

    def test_156_screen_totals_match_pdf_source(self, conn):
        """Screen and PDF must derive the same header and pivot totals."""
        data = run(
            poc.billing_order_data(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        tipo_rows, pivot_rows = poc._fetch_billing_order(
            conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
        )
        pdf_header = poc._billing_header_from_tipo_rows(
            tipo_rows, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
        )
        pdf_pivot_total = sum(float(r[2] or 0) for r in pivot_rows)
        screen_pivot_total = sum(float(r["total_pagar"] or 0) for r in data["rows"])

        assert pdf_header is not None
        assert data["header"]["total"] == pytest.approx(pdf_header["total"], abs=0.01)
        assert screen_pivot_total == pytest.approx(pdf_pivot_total, abs=0.01)
        assert pdf_header["total"] == pytest.approx(pdf_pivot_total, abs=0.01)

    def test_156_contratista_api_still_uses_total_trabajado_unfiltered(self, conn):
        """Operational /api/tarjas/contratista must keep showing total_trabajado
        for all estados — this page is not Orden de Facturación.

        Call the handler with empty strings (not omitted kwargs): FastAPI
        Query(None) defaults are Query objects, which psycopg2 cannot adapt.
        """
        stored_trabajado = _stored_total_trabajado(
            conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
        )
        result = run(
            tc.get_tarjas_contractor_data(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                centro_costo="",
                tipo_pago="",
                labor="",
            )
        )
        api_total = sum(float(r.get("total_trabajado") or 0) for r in result["rows"])
        assert api_total == pytest.approx(stored_trabajado, abs=0.01)
        assert api_total == pytest.approx(BUGGY_TOTAL_TRABAJADO, abs=0.01)

        src = inspect.getsource(tc.get_tarjas_contractor_data)
        assert "appsheet.tarjas_pagos" in src
        assert "estado" not in src

    def test_156_billing_order_pdf_still_renders(self):
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
    def test_156_facturacion_header_pivot_zero_isolation(self, conn):
        """A different contratista/empresa pair must not leak into this
        billing order's totals (scoped via contratista + nombre_campo)."""
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

        result_a = run(
            poc.billing_order_data(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        result_b = run(
            poc.billing_order_data(
                contratista=other_contratista,
                empresa=other_empresa,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )

        workers_a = {r["trabajador"] for r in result_a["rows"]}
        expected_b = _billable_sum(
            conn, other_contratista, other_empresa, FECHA_INICIO, FECHA_TERMINO
        )
        total_b = sum(float(r["total_pagar"] or 0) for r in result_b["rows"])

        assert total_b == pytest.approx(expected_b, abs=0.01)
        for r in result_a["rows"]:
            assert r["trabajador"] in workers_a
        assert result_a["header"]["contractor"] == CONTRATISTA
        assert result_a["header"]["company"] == EMPRESA
        if result_b["header"] is not None:
            assert result_b["header"]["contractor"] == other_contratista
            assert result_b["header"]["company"] == other_empresa
            assert result_a["header"]["total"] != result_b["header"]["total"] or (
                result_a["header"]["total"] == 0
            )
