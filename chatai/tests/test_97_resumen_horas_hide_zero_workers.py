"""
Regression tests for issue #97: the "Detalle trabajador hora extra" report
(a.k.a. "Horas extra por persona", /tarjas/resumen-horas) showed every worker
with any payment record (tarjas_pagos) in the queried date range, even when
their horas_extras total for the whole period was 0 — flooding the report
with zero-rows.

Fix: the 3 endpoints behind this report (screen JSON, Excel, PDF) now drop
workers whose horas_extras SUM across the entire period (all tipo_pago +
dates combined) is 0. A worker with overtime on some days but not others
still appears in full, including their zero days — only workers with a
grand total of exactly 0 are excluded. An explanatory note was also added on
screen and in the PDF: "*Sólo se muestran aquellos trabajadores que cuentan
con horas extras en el periodo especificado."

Ground truth used below (real data, contratista='HERBI ML SPA',
2026-07-01..2026-08-10): 46 distinct workers, only 4 with horas_extras > 0.
"Cristhian soto morales" (total 17) has BOTH zero-hour and positive-hour
rows in this window — the exact "mixed" case the fix must preserve in full.
All other 42 workers, e.g. "Claudia Donoso", have a total of exactly 0 and
must be excluded entirely.
"""

import asyncio
import io
import os
import sys

import openpyxl
import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc

CONTRATISTA_A = "HERBI ML SPA"
CONTRATISTA_B = "MULTISERVICIOS BONHOMIA SPA"
FECHA_INICIO = "2026-07-01"
FECHA_TERMINO = "2026-08-10"

WORKER_WITH_EXTRA_A = "Cristhian soto morales"  # total 17h, mixed zero/nonzero days
WORKER_ZERO_A = "Claudia Donoso"  # total 0h — must be excluded
WORKER_WITH_EXTRA_B = "Cristian González Dinamarca"  # total 20.5h, contratista B

NOTE_TEXT = (
    "Sólo se muestran aquellos trabajadores que cuentan con horas "
    "extras en el periodo especificado."
)


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


def _worker_total_ground_truth(conn, contratista, trabajador, fecha_inicio, fecha_termino):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(horas_extras), 0)
            FROM appsheet.tarjas_pagos
            WHERE contratista = %s AND trabajador = %s
              AND fecha::date BETWEEN %s AND %s
            """,
            (contratista, trabajador, fecha_inicio, fecha_termino),
        )
        return float(cur.fetchone()[0] or 0)


class TestScreenHidesZeroTotalWorkers:
    def test_97_resumen_horas_regression(self, conn):
        """Workers with a 0 horas_extras total for the whole period must not
        appear on screen; workers with a positive total must."""
        assert (
            _worker_total_ground_truth(
                conn, CONTRATISTA_A, WORKER_ZERO_A, FECHA_INICIO, FECHA_TERMINO
            )
            == 0
        )
        assert (
            _worker_total_ground_truth(
                conn, CONTRATISTA_A, WORKER_WITH_EXTRA_A, FECHA_INICIO, FECHA_TERMINO
            )
            > 0
        )

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
        trabajadores = {r["trabajador"] for r in result["rows"]}
        assert WORKER_ZERO_A not in trabajadores
        assert WORKER_WITH_EXTRA_A in trabajadores

    def test_97_resumen_horas_keeps_zero_days_for_mixed_worker_regression(self, conn):
        """A worker with overtime on some days but not others must keep ALL
        their rows, including the zero-hour ones — only the row-per-worker
        aggregate decides inclusion, not a per-row filter."""
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
        assert rows, "expected rows for a worker with a positive total"
        hours = [float(r["horas_trabajadas"] or 0) for r in rows]
        assert any(h == 0 for h in hours), "zero-hour days must be preserved"
        assert any(h > 0 for h in hours)
        expected_total = _worker_total_ground_truth(
            conn, CONTRATISTA_A, WORKER_WITH_EXTRA_A, FECHA_INICIO, FECHA_TERMINO
        )
        assert sum(hours) == pytest.approx(expected_total)


class TestExcelHidesZeroTotalWorkers:
    def test_97_resumen_horas_excel_regression(self):
        resp = run(
            tc.download_tarjas_resumen_horas_excel(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                trabajador=None,
                tipo_pago=None,
                contratista=CONTRATISTA_A,
                empresa=None,
            )
        )
        body = run(_body_bytes(resp))
        wb = openpyxl.load_workbook(io.BytesIO(body))
        ws = wb.active
        names = {row[0].value for row in ws.iter_rows(min_row=2) if row[0].value}
        assert WORKER_ZERO_A not in names
        assert WORKER_WITH_EXTRA_A in names


class TestPdfHidesZeroTotalWorkersAndShowsNote:
    def _text(self, resp) -> str:
        import fitz

        body = run(_body_bytes(resp))
        doc = fitz.open(stream=body, filetype="pdf")
        return "".join(page.get_text() for page in doc)

    def setup_method(self, _method=None):
        # _pdf_header() uses strftime("%-d de %B de %Y"), a Linux/macOS-only
        # directive that raises ValueError on Windows — unrelated to issue
        # #97. Stub it out the same way test_54_pdf_titles_contratista.py
        # does, so these tests run on any platform.
        self._orig_header = tc._pdf_header
        tc._pdf_header = (
            lambda title, fi, ft, filtros, *a, **kw: f"<h1>{title}</h1><p>{fi}-{ft}</p>"
        )

    def teardown_method(self, _method=None):
        tc._pdf_header = self._orig_header

    def test_97_resumen_horas_pdf_regression(self):
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
        assert WORKER_ZERO_A not in text
        assert WORKER_WITH_EXTRA_A in text

    def test_97_resumen_horas_pdf_shows_explanatory_note_regression(self):
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
        assert NOTE_TEXT in text


class TestScreenNoteInTemplate:
    def test_97_resumen_horas_html_shows_explanatory_note_regression(self):
        """Screen template must render the same explanatory note as the PDF."""
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "frontend",
            "templates",
            "tarjas_resumen_horas.html",
        )
        with open(path, encoding="utf-8") as f:
            source = f.read()
        assert NOTE_TEXT in source


class TestCrossContratistaIsolation:
    def test_97_resumen_horas_scoped_to_contratista_isolation(self):
        """The zero-total filter must be computed within each contratista's
        own scoped query — a worker with overtime for one contratista must
        never leak into another contratista's filtered result, and vice
        versa (tenant scoping via WHERE contratista = %s)."""
        result_a = run(
            tc.get_tarjas_resumen_horas(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                trabajador=None,
                tipo_pago=None,
                contratista=CONTRATISTA_A,
                empresa=None,
            )
        )
        result_b = run(
            tc.get_tarjas_resumen_horas(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                trabajador=None,
                tipo_pago=None,
                contratista=CONTRATISTA_B,
                empresa=None,
            )
        )
        trabajadores_a = {r["trabajador"] for r in result_a["rows"]}
        trabajadores_b = {r["trabajador"] for r in result_b["rows"]}

        assert WORKER_WITH_EXTRA_A in trabajadores_a
        assert WORKER_WITH_EXTRA_A not in trabajadores_b
        assert WORKER_WITH_EXTRA_B in trabajadores_b
        assert WORKER_WITH_EXTRA_B not in trabajadores_a
