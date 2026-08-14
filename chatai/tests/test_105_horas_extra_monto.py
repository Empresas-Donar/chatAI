"""
Regression tests for issue #105: the "Detalle trabajador hora extra" report
(a.k.a. "Horas extra por persona", /tarjas/resumen-horas) now shows, on
screen and in the PDF:

1. A "Monto" column per worker with the money value of their overtime hours
   for the period (appsheet.tarjas_pagos.total_hora_extra, summed the same
   way as horas_extras — no rate is derived, the source column already
   holds the peso amount).
2. A summary box above the table with the total overtime hours, the count
   of workers receiving overtime, and the total money to be paid, scoped to
   the currently applied filters.

Ground truth used below (real data, contratista='HERBI ML SPA',
2026-07-01..2026-08-10): 4 workers with horas_extras > 0 —
Cristhian soto morales (17h / $57.800), Maibet Lobo (4h / $13.600),
MAIBET LOBOS (3h / $10.200), Pedro Gutiérrez Valenzuela (1h / $3.400) —
totalling 25h / $85.000.
"""

import asyncio
import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc

CONTRATISTA_A = "HERBI ML SPA"
FECHA_INICIO = "2026-07-01"
FECHA_TERMINO = "2026-08-10"

WORKER_WITH_EXTRA_A = "Cristhian soto morales"

EXPECTED_TOTAL_HORAS = 25
EXPECTED_TOTAL_TRABAJADORES = 4
EXPECTED_TOTAL_MONTO = 85000
EXPECTED_WORKER_MONTO = 57800


def run(coro):
    return asyncio.run(coro)


async def _body_bytes(resp):
    if getattr(resp, "body", None):
        return resp.body
    return b"".join([c async for c in resp.body_iterator])


@pytest.fixture
def conn():
    c = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    yield c
    c.rollback()
    c.close()


def _worker_monto_ground_truth(conn, contratista, trabajador, fecha_inicio, fecha_termino):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(total_hora_extra), 0)
            FROM appsheet.tarjas_pagos
            WHERE contratista = %s AND trabajador = %s
              AND fecha::date BETWEEN %s AND %s
            """,
            (contratista, trabajador, fecha_inicio, fecha_termino),
        )
        return float(cur.fetchone()[0] or 0)


class TestScreenResumenAndMonto:
    def test_105_resumen_totals_regression(self, conn):
        result = run(
            tc.get_tarjas_resumen_horas(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                trabajador=None,
                tipo_pago=None,
                contratista=CONTRATISTA_A,
                empresa=None,
            )
        )
        resumen = result["resumen"]
        assert resumen["total_horas"] == pytest.approx(EXPECTED_TOTAL_HORAS)
        assert resumen["total_trabajadores"] == EXPECTED_TOTAL_TRABAJADORES
        assert resumen["total_monto"] == pytest.approx(EXPECTED_TOTAL_MONTO)

    def test_105_screen_row_monto_matches_ground_truth_regression(self, conn):
        result = run(
            tc.get_tarjas_resumen_horas(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                trabajador=WORKER_WITH_EXTRA_A,
                tipo_pago=None,
                contratista=CONTRATISTA_A,
                empresa=None,
            )
        )
        rows = result["rows"]
        assert rows
        total_monto = sum(float(r["monto_hora_extra"] or 0) for r in rows)
        expected = _worker_monto_ground_truth(
            conn, CONTRATISTA_A, WORKER_WITH_EXTRA_A, FECHA_INICIO, FECHA_TERMINO
        )
        assert total_monto == pytest.approx(expected)
        assert total_monto == pytest.approx(EXPECTED_WORKER_MONTO)


class TestPdfSummaryAndMontoColumn:
    def _text(self, resp) -> str:
        import fitz

        body = run(_body_bytes(resp))
        doc = fitz.open(stream=body, filetype="pdf")
        return "".join(page.get_text() for page in doc)

    def setup_method(self, _method=None):
        # _pdf_header() uses strftime("%-d de %B de %Y"), a Linux/macOS-only
        # directive that raises ValueError on Windows — unrelated to this
        # issue. Stub it out the same way test_97 does.
        self._orig_header = tc._pdf_header
        tc._pdf_header = (
            lambda title, fi, ft, filtros, *a, **kw: f"<h1>{title}</h1><p>{fi}-{ft}</p>"
        )

    def teardown_method(self, _method=None):
        tc._pdf_header = self._orig_header

    def test_105_pdf_shows_summary_box_regression(self):
        resp = run(
            tc.download_tarjas_resumen_horas_pdf(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                trabajador=None,
                tipo_pago=None,
                contratista=CONTRATISTA_A,
                empresa=None,
            )
        )
        text = self._text(resp)
        assert str(EXPECTED_TOTAL_HORAS) in text
        assert str(EXPECTED_TOTAL_TRABAJADORES) in text
        assert "85.000" in text

    def test_105_pdf_shows_worker_monto_column_regression(self):
        resp = run(
            tc.download_tarjas_resumen_horas_pdf(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                trabajador=WORKER_WITH_EXTRA_A,
                tipo_pago=None,
                contratista=CONTRATISTA_A,
                empresa=None,
            )
        )
        text = self._text(resp)
        assert "57.800" in text
