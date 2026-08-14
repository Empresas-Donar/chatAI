"""
Regression tests for issue #96: the "Detalle Operacional" PDF
(/api/tarjas/detalle/download-pdf) must show the same Resumen table as
the on-screen "Detalle de la semana" report.

The pie chart originally added for #96 was removed in issue #122 — see
test_122_pdf_detalle_sin_grafico.py for that and other #122 coverage
(the % column in Resumen, the Detalle column changes, and the % pago
formula fix).
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc
from db import get_connection


class TestTipoPagoHelpers:
    """The PDF summary/chart must mirror TIPO_LABELS / TIPO_CLASS in
    tarjas_detail.js exactly, including the fallback for tipo_pago values
    outside trato/Al dia (e.g. Tractorista, Bono)."""

    def test_96_label_trato(self):
        assert tc._tipo_pago_label("trato") == "Trato"

    def test_96_label_al_dia_variants(self):
        assert tc._tipo_pago_label("Al dia") == "Al Día"
        assert tc._tipo_pago_label("Al día") == "Al Día"

    def test_96_label_fallback_passthrough(self):
        assert tc._tipo_pago_label("Tractorista") == "Tractorista"
        assert tc._tipo_pago_label("Bono") == "Bono"

    def test_96_badge_class_trato_and_aldia(self):
        assert tc._tipo_pago_badge_class("trato") == "badge-trato"
        assert tc._tipo_pago_badge_class("Al dia") == "badge-aldia"
        assert tc._tipo_pago_badge_class("Al día") == "badge-aldia"

    def test_96_badge_class_fallback_empty(self):
        assert tc._tipo_pago_badge_class("Tractorista") == ""
        assert tc._tipo_pago_badge_class("Bono") == ""


class TestSummaryTableHtml:
    def test_96_renders_rows_badge_and_total(self):
        resumen = [
            {"tipo_pago": "trato", "total_pagar": 1000000, "jornadas": 10},
            {"tipo_pago": "Al dia", "total_pagar": 500000, "jornadas": 5},
        ]
        html = tc._summary_table_html(resumen, 1500000, 15)
        assert "Trato" in html
        assert "Al Día" in html
        assert "badge-trato" in html
        assert "badge-aldia" in html
        assert "$1.000.000" in html
        assert "$1.500.000" in html  # Total row


class TestDownloadPdfIntegration:
    """End-to-end: the generated PDF bytes must contain the Resumen table
    and an embedded chart image, mirroring what the screen shows."""

    def _pdf_bytes(self, resp) -> bytes:
        import asyncio

        async def _bytes():
            if getattr(resp, "body", None):
                return resp.body
            return b"".join([c async for c in resp.body_iterator])

        return asyncio.run(_bytes())

    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)

    def setup_method(self, monkeypatch=None):
        # _pdf_header() uses strftime("%-d ...") which is a glibc-only format
        # code — unrelated to issue #96, but it makes the header unusable for
        # a plain-Python test on some platforms, so stub it the same way
        # test_54_pdf_titles_contratista.py does.
        self._orig_header = tc._pdf_header
        tc._pdf_header = lambda title, fi, ft, filtros, *a, **kw: (
            f"<h1>{title}</h1><p>{fi}-{ft}</p>"
        )

    def teardown_method(self, monkeypatch=None):
        tc._pdf_header = self._orig_header

    def test_96_detalle_pdf_includes_resumen_regression(self):
        """The original bug: the Detalle Operacional PDF only rendered the
        Detalle table, missing the Resumen table shown on screen. This must
        no longer be the case, and the PDF must not raise."""
        resp = self._run(
            tc.download_tarjas_detalle_pdf(
                fecha_inicio="2026-07-01",
                fecha_termino="2026-07-31",
                contratista=None,
                centro_costo=None,
                tipo_pago=None,
                labor=None,
                campo=None,
                empresa=None,
            )
        )
        body = self._pdf_bytes(resp)
        assert body[:4] == b"%PDF"

        import fitz

        doc = fitz.open(stream=body, filetype="pdf")
        text = doc[0].get_text()
        assert "Resumen" in text
        assert "Tipo de pago" in text
        assert "Total a pagar" in text
        assert "Jornadas" in text
        assert "Detalle" in text  # detail section title still present

    def test_96_detalle_pdf_empty_result_does_not_raise(self):
        """A date range with no rows must not crash on the resumen/chart
        section (division by zero when total == 0)."""
        resp = self._run(
            tc.download_tarjas_detalle_pdf(
                fecha_inicio="1999-01-01",
                fecha_termino="1999-01-02",
                contratista=None,
                centro_costo=None,
                tipo_pago=None,
                labor=None,
                campo=None,
                empresa=None,
            )
        )
        body = self._pdf_bytes(resp)
        assert body[:4] == b"%PDF"


class TestCampoIsolation:
    """appsheet.tarjas_reporte spans multiple campos (predios) — the closest
    analog to farm isolation in this platform. Filtering the Detalle PDF's
    resumen/chart data by one campo must not leak totals from another."""

    def _resumen_for_campo(self, campo: str):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                where, params = tc._build_detalle_filters(
                    "2026-07-01", "2026-07-31", campo=campo
                )
                return tc._query_detalle_resumen(cur, where, params)
        finally:
            conn.close()

    def test_96_campo_filter_isolation_regression(self):
        resumen_a = self._resumen_for_campo("ISLA DE MAIPO")
        resumen_b = self._resumen_for_campo("TALAGANTE")

        total_a = sum(float(r["total_pagar"] or 0) for r in resumen_a)
        total_b = sum(float(r["total_pagar"] or 0) for r in resumen_b)

        # Both campos have data in this range (fixture data verified against
        # the real DB) and must not be equal to each other nor to the
        # unfiltered (all-campos) total — otherwise the campo filter isn't
        # actually scoping the resumen query.
        assert total_a > 0
        assert total_b > 0
        assert total_a != total_b

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                where, params = tc._build_detalle_filters("2026-07-01", "2026-07-31")
                resumen_all = tc._query_detalle_resumen(cur, where, params)
        finally:
            conn.close()
        total_all = sum(float(r["total_pagar"] or 0) for r in resumen_all)

        assert total_a < total_all
        assert total_b < total_all
        assert total_a + total_b <= total_all
