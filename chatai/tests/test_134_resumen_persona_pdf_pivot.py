"""
Regression tests for issue #134: the "Resumen por persona" PDF used a flat
list layout (one row per trabajador+tipo_pago+fecha), unlike the on-screen
pivot (/tarjas/resumen-persona) which shows one column per date. The user
asked for the PDF to match the screen exactly: "debe ser cada fecha una
columna".

Root cause: an old comment claimed "xhtml2pdf cannot reliably render wide
pivot tables" — no longer true, since Detalle Contratistas / Horas Extra /
Hora Ponderada 9h already use _pivot_col_widths() successfully (issues #52,
#132). Converted to the same pattern. The endpoint also didn't include
_PDF_CSS at all before this fix (needed for the .pivot-wide table class).
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc

CONTRATISTA = "HERBI ML SPA"
EMPRESA = "TALAGANTE"
FECHA_INICIO = "2026-08-12"
FECHA_TERMINO = "2026-08-18"


def run(coro):
    return asyncio.run(coro)


async def _body_bytes(resp):
    if getattr(resp, "body", None):
        return resp.body
    return b"".join([c async for c in resp.body_iterator])


class TestResumenPersonaBuilderIsPivot:
    def test_134_html_has_one_column_per_date_not_flat_rows(self):
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
                html = tc._build_resumen_persona_html(
                    cur, FECHA_INICIO, FECHA_TERMINO, contratista=CONTRATISTA, empresa=EMPRESA
                )
        finally:
            conn.rollback()
            conn.close()

        # Pivot markers: the shared date-pivot table class, a date header
        # per day in the range, and a single Total column — not the old
        # flat list's "Fecha"/"Monto"/"Subtotal" columns.
        assert "pivot-wide" in html
        assert ">Total<" in html
        for d in ["12/08", "13/08", "14/08", "15/08", "16/08", "17/08", "18/08"]:
            assert f">{d}<" in html
        assert "Subtotal" not in html
        assert "<th" in html and ">Fecha</th>" not in html
        assert ">Monto</th>" not in html

    def test_134_worker_row_appears_once_not_once_per_date(self):
        """The old flat layout repeated the worker name across many rows
        (one per date with a nonzero value); the pivot shows it once."""
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
                html = tc._build_resumen_persona_html(
                    cur,
                    FECHA_INICIO,
                    FECHA_TERMINO,
                    trabajador="MARIO MERCADO",
                    contratista=CONTRATISTA,
                    empresa=EMPRESA,
                )
        finally:
            conn.rollback()
            conn.close()

        assert html.count("MARIO MERCADO") == 1


class TestResumenPersonaPdfIntegration:
    def test_134_pdf_renders_and_contains_date_columns_regression(self):
        resp = run(
            tc.download_tarjas_resumen_persona_pdf(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                trabajador=None,
                tipo_pago=None,
                contratista=CONTRATISTA,
                empresa=EMPRESA,
            )
        )
        # StreamingResponse.body_iterator can only be consumed once — pull
        # the bytes a single time and reuse them for both checks below.
        body = run(_body_bytes(resp))
        assert body[:4] == b"%PDF"

        import fitz

        doc = fitz.open(stream=body, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        assert "12/08" in text
        assert "Total" in text

    def test_134_wide_date_range_rejected_not_garbled(self):
        """Same _check_pivot_date_range guard the other pivots use — a wide
        range must fail cleanly (400) instead of producing a broken PDF."""
        import asyncio as _asyncio

        import pytest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _asyncio.run(
                tc.download_tarjas_resumen_persona_pdf(
                    fecha_inicio="2026-01-01",
                    fecha_termino="2026-07-28",
                    trabajador=None,
                    tipo_pago=None,
                    contratista=None,
                    empresa=None,
                )
            )
        assert exc.value.status_code == 400


class TestBulkPdfSharesSamePivot:
    def test_134_bulk_section_matches_standalone_builder(self):
        """Same guarantee as issue #116 for the other 9 reports: the bulk
        /reportes section and the standalone builder must be identical."""
        import controllers.reports_controller as rc
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
                expected = tc._build_resumen_persona_html(
                    cur, FECHA_INICIO, FECHA_TERMINO, contratista=CONTRATISTA, empresa=EMPRESA
                )
            with conn.cursor() as cur:
                actual = rc._REPORT_GENERATORS["resumen-persona"](
                    cur, FECHA_INICIO, FECHA_TERMINO, EMPRESA, CONTRATISTA
                )
        finally:
            conn.rollback()
            conn.close()
        assert actual == expected
