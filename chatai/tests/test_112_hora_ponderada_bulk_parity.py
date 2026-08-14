"""
Regression tests for issue #112: the "Hora ponderada 9h" section of the
bulk /reportes PDF (added in issue #109) was written before issue #108
fixed the standalone /tarjas/hora-ponderada-9h/download-pdf, so the two
diverged (missing highlighting, missing date-range cap, footer cells
missing the width style that caused #108's broken-layout bug).

Superseded by issue #116: reports_controller.py no longer keeps a
duplicated _html_hora_ponderada / _HORA_PONDERADA_HIGHLIGHT_THRESHOLD /
_MAX_PIVOT_DATES_HORA_PONDERADA of its own — the bulk section is produced
by tarjas_controller._build_hora_ponderada_html directly (via
rc._REPORT_GENERATORS["hora-ponderada-9h"]), the exact same function the
standalone PDF endpoint calls. This file's checks now hold true by
construction, but are kept as a regression net against someone
reintroducing a local, divergent copy in reports_controller.py.
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
    orig_tc = tc._pdf_header
    tc._pdf_header = lambda title, fi, ft, filtros, *a, **kw: f"<h1>{title}</h1>"
    yield
    tc._pdf_header = orig_tc


def _hora_ponderada_bulk(cur, fecha_inicio, fecha_termino, empresa, contratista=None):
    return rc._REPORT_GENERATORS["hora-ponderada-9h"](
        cur, fecha_inicio, fecha_termino, empresa, contratista
    )


class TestDateRangeCapMatchesStandalone:
    def test_112_bulk_caps_at_23_days_same_as_standalone_regression(self, conn):
        with conn.cursor() as cur, pytest.raises(HTTPException) as exc:
            _hora_ponderada_bulk(cur, "2026-07-01", "2026-08-10", None, None)
        assert exc.value.status_code == 400
        assert "23 días" in exc.value.detail


class TestHighlightMatchesStandalone:
    def test_112_bulk_highlights_values_above_threshold_regression(self, conn):
        with conn.cursor() as cur:
            html = _hora_ponderada_bulk(
                cur, FECHA_INICIO, FECHA_TERMINO, None, CONTRATISTA_HIGH
            )
        assert "background:#ffedd5;color:#c2410c;font-weight:bold;" in html

    def test_112_bulk_footer_cells_all_carry_width_style_regression(self, conn):
        """Root cause of the #108 layout bug: any <td> in the footer row
        without an explicit width style breaks xhtml2pdf's fixed-table
        layout for the whole table. Every date cell in the footer must
        carry the same style="width:...%" as the header/body date cells."""
        with conn.cursor() as cur:
            html = _hora_ponderada_bulk(
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
            bulk_html = _hora_ponderada_bulk(
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
