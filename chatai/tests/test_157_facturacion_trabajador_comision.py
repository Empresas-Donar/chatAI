"""
Regression tests for Orden de Facturación worker-pay vs commission split.

The pivot and Total a Pagar already include contractor commission
(total_pagar = total_trabajado + total_contratista). The contractor needs
to see both: what goes to the worker and the billed total with commission.

Known dataset (HERBI ML SPA / KONTROLAG / 2026-08-26..2026-09-01):
  total_trabajado   = 175_000
  total_contratista =  87_500
  total_pagar       = 262_500
"""

import asyncio
import inspect
import os
import sys
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.purchase_orders_controller as poc

CONTRATISTA = "HERBI ML SPA"
EMPRESA = "KONTROLAG"
FECHA_INICIO = "2026-08-26"
FECHA_TERMINO = "2026-09-01"

EXPECTED_TRABAJADO = 175_000.0
EXPECTED_COMISION = 87_500.0
EXPECTED_BILLABLE = 262_500.0

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


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


class TestWorkerCommissionSplit:
    def test_157_api_exposes_worker_and_commission(self, conn):
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
        assert header["total_trabajado"] == pytest.approx(EXPECTED_TRABAJADO, abs=0.01)
        assert header["total_contratista"] == pytest.approx(EXPECTED_COMISION, abs=0.01)
        assert header["total"] == pytest.approx(EXPECTED_BILLABLE, abs=0.01)
        assert header["total"] == pytest.approx(
            header["total_trabajado"] + header["total_contratista"], abs=0.01
        )
        assert header["pct_comision"] == pytest.approx(50.0, abs=0.01)
        assert header["pct_comision_al_dia"] == pytest.approx(50.0, abs=0.01)
        assert header["pct_comision_trato"] is None

        assert "total_trabajado" in result["columns"]
        assert "total_contratista" in result["columns"]

        sum_trab = sum(float(r["total_trabajado"] or 0) for r in result["rows"])
        sum_com = sum(float(r["total_contratista"] or 0) for r in result["rows"])
        sum_pagar = sum(float(r["total_pagar"] or 0) for r in result["rows"])
        assert sum_trab == pytest.approx(EXPECTED_TRABAJADO, abs=0.01)
        assert sum_com == pytest.approx(EXPECTED_COMISION, abs=0.01)
        assert sum_pagar == pytest.approx(EXPECTED_BILLABLE, abs=0.01)
        assert sum_pagar == pytest.approx(header["total"], abs=0.01)

    def test_157_fetch_keeps_billable_at_index_2(self, conn):
        """Existing tests and PDF header read r[2] as the billable total."""
        _tipo_rows, pivot_rows = poc._fetch_billing_order(
            conn, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
        )
        assert pivot_rows
        for row in pivot_rows:
            assert len(row) >= 5
            billable = float(row[2] or 0)
            trabajado = float(row[3] or 0)
            comision = float(row[4] or 0)
            assert billable == pytest.approx(trabajado + comision, abs=0.01)

        pivot_total = sum(float(r[2] or 0) for r in pivot_rows)
        assert pivot_total == pytest.approx(EXPECTED_BILLABLE, abs=0.01)

    def test_157_pdf_renders_split_and_still_produces_pdf(self):
        src = inspect.getsource(poc.billing_order_pdf)
        assert "Total trabajadores" in src
        assert "Subtotal" in src
        assert "Adicional" in src
        assert ">Suma</th>" in src or "Suma</th>" in src
        assert "_fmt_pct" in src
        assert "_tipo_badges_html" in src
        assert "_fmt_pivot_cell" not in src

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

    def test_157_fmt_pct(self):
        assert poc._fmt_pct(50) == "50%"
        assert poc._fmt_pct(33.3) == "33,3%"
        assert poc._fmt_pct(None) == "—"
        assert poc._pct(87_500, 175_000) == 50.0
        assert poc._pct(0, 0) is None
        html = poc._tipo_badges_html(["trato"])
        assert "Trato" in html
        html = poc._tipo_badges_html(["Al dia"])
        assert "Al día" in html

    def test_157_ui_shows_worker_pay_and_summary(self):
        js = (FRONTEND / "static" / "billing_order.js").read_text()
        html = (FRONTEND / "templates" / "billing_order.html").read_text()
        assert "doc-subtotal" in html
        assert "doc-summary-comision" in html
        assert "doc-summary-total" in html
        assert "Subtotal" in html
        assert "bo-pivot-legend" not in html
        assert "cell-worker-pay" not in js
        assert "total_trabajado" in js
        assert "total_contratista" in js
        assert "doc-pct-comision" in html
        assert "doc-pct-trato" in html
        assert "doc-pct-aldia" in html
        assert "fmtPct" in js
        assert "function toISO" in js
        assert "badge-trato" in js
        assert "badge-aldia" in js


class TestCrossFarmIsolation:
    def test_157_facturacion_trabajador_comision_isolation(self, conn):
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
        assert row is not None, "expected another contratista/empresa pair"
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

        trab_a = sum(float(r["total_trabajado"] or 0) for r in result_a["rows"])
        trab_b = sum(float(r["total_trabajado"] or 0) for r in result_b["rows"])
        assert trab_a == pytest.approx(EXPECTED_TRABAJADO, abs=0.01)
        assert result_a["header"]["contractor"] == CONTRATISTA
        if result_b["header"] is not None:
            assert result_b["header"]["contractor"] == other_contratista
            assert result_a["header"]["total_trabajado"] != pytest.approx(
                trab_b, abs=0.01
            ) or result_a["header"]["total"] == 0
