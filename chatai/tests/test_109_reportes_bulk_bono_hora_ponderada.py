"""
Regression tests for issue #109: the "Descarga de Reportes" bulk-PDF page
(/reportes) was missing the two newest Tarjas — Contratistas reports —
Bonos mensuales (issue #100) and Hora ponderada 9h (issue #102) — from its
selectable report list.

Updated by issue #116: reports_controller.py no longer keeps its own
duplicated _html_bono_mensual/_html_hora_ponderada functions — it imports
tarjas_controller.py's shared builders (_build_bono_mensual_html /
_build_hora_ponderada_html), so this file now exercises those through
rc._REPORT_GENERATORS instead of calling removed rc._html_* functions
directly. "Bonos mensuales" normally filters by a whole calendar month
(mes=YYYY-MM) on its own page; in the bulk PDF it uses the same
fecha_inicio/fecha_termino range as every other report instead.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.reports_controller as rc
import controllers.tarjas_controller as tc

FECHA_INICIO = "2026-01-01"
FECHA_TERMINO = "2026-12-31"


def run(coro):
    return asyncio.run(coro)


async def _body_bytes(resp):
    if getattr(resp, "body", None):
        return resp.body
    return b"".join([c async for c in resp.body_iterator])


class TestReportsRegistered:
    def test_109_bono_mensual_listed_regression(self):
        ids = {r["id"] for r in rc.AVAILABLE_REPORTS}
        assert "bono-mensual" in ids
        entry = next(r for r in rc.AVAILABLE_REPORTS if r["id"] == "bono-mensual")
        assert entry["category"] == "Tarjas — Contratistas"

    def test_109_hora_ponderada_listed_regression(self):
        ids = {r["id"] for r in rc.AVAILABLE_REPORTS}
        assert "hora-ponderada-9h" in ids
        entry = next(
            r for r in rc.AVAILABLE_REPORTS if r["id"] == "hora-ponderada-9h"
        )
        assert entry["category"] == "Tarjas — Contratistas"

    def test_109_generators_registered_regression(self):
        assert "bono-mensual" in rc._REPORT_GENERATORS
        assert "hora-ponderada-9h" in rc._REPORT_GENERATORS


class TestGeneratorsProduceHtml:
    def setup_method(self, _method=None):
        # _pdf_header() uses strftime("%-d de %B de %Y"), a Linux/macOS-only
        # directive that raises ValueError on Windows — unrelated to this
        # issue. Stub it on tarjas_controller, which is where _pdf_header
        # now actually lives (reports_controller imports it, per #116).
        self._orig_header = tc._pdf_header
        tc._pdf_header = (
            lambda title, fi, ft, filtros, *a, **kw: f"<h1>{title}</h1>"
        )

    def teardown_method(self, _method=None):
        tc._pdf_header = self._orig_header

    def test_109_html_bono_mensual_uses_date_range_not_month(self):
        """Must filter by the given fecha_inicio/fecha_termino range and
        labor = 'Bono mensual', not force a single calendar month."""
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(total_pagar), 0) FROM appsheet.tarjas_pagos "
                    "WHERE labor = 'Bono mensual' AND fecha::date BETWEEN %s AND %s",
                    (FECHA_INICIO, FECHA_TERMINO),
                )
                expected_total = float(cur.fetchone()[0] or 0)

                html = rc._REPORT_GENERATORS["bono-mensual"](
                    cur, FECHA_INICIO, FECHA_TERMINO, None, None
                )
        finally:
            conn.rollback()
            conn.close()

        assert "Bonos Mensuales" in html
        assert "Suma total" in html
        if expected_total:
            formatted = f"${int(expected_total):,}".replace(",", ".")
            assert formatted in html

    def test_109_html_hora_ponderada_produces_pivot(self):
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        try:
            with conn.cursor() as cur:
                html = rc._REPORT_GENERATORS["hora-ponderada-9h"](
                    cur, "2026-07-01", "2026-07-15", None, "HERBI ML SPA"
                )
        finally:
            conn.rollback()
            conn.close()

        assert "Hora Ponderada 9h" in html
        assert "pivot-wide" in html
        assert "Hora ponderada 9h global" in html


class TestBulkPdfEndpointIntegration:
    def setup_method(self, _method=None):
        self._orig_header = tc._pdf_header
        tc._pdf_header = (
            lambda title, fi, ft, filtros, *a, **kw: f"<h1>{title}</h1>"
        )

    def teardown_method(self, _method=None):
        tc._pdf_header = self._orig_header

    def _text(self, resp) -> str:
        import fitz

        body = run(_body_bytes(resp))
        doc = fitz.open(stream=body, filetype="pdf")
        return "".join(page.get_text() for page in doc)

    def test_109_bulk_pdf_accepts_bono_mensual_regression(self):
        resp = run(
            rc.bulk_pdf_download(
                reports="bono-mensual",
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                empresa=None,
                contratista=None,
            )
        )
        text = self._text(resp)
        assert "Bonos Mensuales" in text

    def test_109_bulk_pdf_accepts_hora_ponderada_regression(self):
        resp = run(
            rc.bulk_pdf_download(
                reports="hora-ponderada-9h",
                fecha_inicio="2026-07-01",
                fecha_termino="2026-07-15",
                empresa=None,
                contratista="HERBI ML SPA",
            )
        )
        text = self._text(resp)
        assert "Hora Ponderada 9h" in text

    def test_109_bulk_pdf_combines_both_new_reports_with_existing_regression(self):
        """Selecting the two new reports alongside a pre-existing one must
        not error — same page_break-joined-sections mechanism as before."""
        resp = run(
            rc.bulk_pdf_download(
                reports="resumen-horas,bono-mensual,hora-ponderada-9h",
                fecha_inicio="2026-07-01",
                fecha_termino="2026-07-15",
                empresa=None,
                contratista="HERBI ML SPA",
            )
        )
        text = self._text(resp)
        assert "Horas Extra" in text
        assert "Bonos Mensuales" in text
        assert "Hora Ponderada 9h" in text
