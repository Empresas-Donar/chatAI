"""
Regression tests for issue #112: the "Hora ponderada 9h" section of the
bulk /reportes PDF (added in issue #109) was written before issue #108
fixed the standalone /tarjas/hora-ponderada-9h/download-pdf, so the two
diverged:

- The standalone PDF highlights daily cells above
  HORA_PONDERADA_HIGHLIGHT_THRESHOLD ($30.000); the bulk version didn't.
- The standalone PDF caps the date range at MAX_PIVOT_DATES_HORA_PONDERADA
  (23 days) with a friendly error suggesting Excel, and gives every footer
  cell an explicit width style (the #108 bug was a footer row missing that
  style, which breaks xhtml2pdf's fixed-table layout for the WHOLE table).
  The bulk version had neither.

This file locks the bulk generator (_html_hora_ponderada in
reports_controller.py) to the same behavior, values, and safety guards as
tarjas_controller.download_tarjas_hora_ponderada_pdf.
"""

import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.reports_controller as rc
import controllers.tarjas_controller as tc

CONTRATISTA_HIGH = "SERVICIOS AGRICOLAS RD SPA"
FECHA_INICIO = "2026-07-01"
FECHA_TERMINO = "2026-07-15"


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


@pytest.fixture(autouse=True)
def stub_pdf_header():
    orig_rc = rc._pdf_header
    orig_tc = tc._pdf_header
    rc._pdf_header = (
        lambda title, fi, ft, empresa, contratista=None: f"<h1>{title}</h1>"
    )
    tc._pdf_header = lambda title, fi, ft, filtros, *a, **kw: f"<h1>{title}</h1>"
    yield
    rc._pdf_header = orig_rc
    tc._pdf_header = orig_tc


class TestDateRangeCapMatchesStandalone:
    def test_112_bulk_caps_at_23_days_same_as_standalone_regression(self, conn):
        assert rc._MAX_PIVOT_DATES_HORA_PONDERADA == tc.MAX_PIVOT_DATES_HORA_PONDERADA

        with conn.cursor() as cur, pytest.raises(HTTPException) as exc:
            rc._html_hora_ponderada(cur, "2026-07-01", "2026-08-10", None, None)
        assert exc.value.status_code == 400
        assert "23 días" in exc.value.detail


class TestHighlightMatchesStandalone:
    def test_112_bulk_highlights_values_above_threshold_regression(self, conn):
        assert (
            rc._HORA_PONDERADA_HIGHLIGHT_THRESHOLD
            == tc.HORA_PONDERADA_HIGHLIGHT_THRESHOLD
        )
        with conn.cursor() as cur:
            html = rc._html_hora_ponderada(
                cur, FECHA_INICIO, FECHA_TERMINO, None, CONTRATISTA_HIGH
            )
        assert "background:#ffedd5;color:#c2410c;font-weight:bold;" in html

    def test_112_bulk_footer_cells_all_carry_width_style_regression(self, conn):
        """Root cause of the #108 layout bug: any <td> in the footer row
        without an explicit width style breaks xhtml2pdf's fixed-table
        layout for the whole table. Every date cell in the footer must
        carry the same style="width:...%" as the header/body date cells."""
        with conn.cursor() as cur:
            html = rc._html_hora_ponderada(
                cur, FECHA_INICIO, FECHA_TERMINO, None, CONTRATISTA_HIGH
            )
        footer_start = html.index("Hora ponderada 9h global")
        footer_row = html[footer_start : html.index("</tr>", footer_start)]
        # Every <td class="num" ...> in the footer must have a style attr.
        import re

        date_cells = re.findall(r'<td class="num"[^>]*>', footer_row)
        assert date_cells, "expected at least one date footer cell"
        assert all("style=" in cell for cell in date_cells)


class TestValuesMatchStandalonePdf:
    def test_112_bulk_and_standalone_compute_same_hora_ponderada_values(self, conn):
        """The bulk section and the standalone PDF must report identical
        hora_ponderada_9h numbers for the same filters — the whole point
        of a 'unified' report is that it doesn't silently diverge."""
        with conn.cursor() as cur:
            bulk_html = rc._html_hora_ponderada(
                cur, FECHA_INICIO, FECHA_TERMINO, None, CONTRATISTA_HIGH
            )

        import asyncio

        async def _body_bytes(resp):
            if getattr(resp, "body", None):
                return resp.body
            return b"".join([c async for c in resp.body_iterator])

        resp = asyncio.run(
            tc.download_tarjas_hora_ponderada_pdf(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                contratista=CONTRATISTA_HIGH,
                empresa=None,
                centro_costo=None,
                labor=None,
            )
        )
        import fitz

        body = asyncio.run(_body_bytes(resp))
        doc = fitz.open(stream=body, filetype="pdf")
        standalone_text = "".join(page.get_text() for page in doc)

        # $72.000 appears in the fixture data found for this contratista/range
        assert "$72.000" in bulk_html
        assert "72.000" in standalone_text
