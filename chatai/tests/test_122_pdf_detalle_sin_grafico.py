"""
Regression tests for issue #122: the "Detalle Operacional" PDF
(/api/tarjas/detalle/download-pdf).

- The pie chart added in #96 is removed — the Resumen table gets a "%"
  column instead (issue #96 pie chart coverage moved out of
  test_96_pdf_detalle_resumen_grafico.py, which no longer applies).
- The Detalle table drops the "Horas" and "Unitario" columns and gains a
  "Nombre CC" column (appsheet.tarjas_cc.cultivo, joined by id_cc).
- The Detalle table's "% pago" is now the row's total divided by
  (Al Día + Trato) only — not partitioned by the row's own tipo_pago as
  before, and not including other tipo_pago values that exist in
  appsheet.tarjas_reporte (e.g. "Bono", "Tractorista"). This formula
  change is in the query shared with the on-screen page and the Excel
  export, so it applies to all three.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc
from db import get_connection


class TestSummaryTableHtmlPercentColumn:
    def test_122_renders_percent_column_and_values(self):
        resumen = [
            {"tipo_pago": "trato", "total_pagar": 1000000, "jornadas": 10},
            {"tipo_pago": "Al dia", "total_pagar": 500000, "jornadas": 5},
        ]
        html = tc._summary_table_html(resumen, 1500000, 15)
        # issue #132 added an explicit width style to this <th>; match the
        # header text loosely instead of the exact (now wider) tag.
        assert ">%</th>" in html
        assert "66.7 %" in html  # 1,000,000 / 1,500,000
        assert "33.3 %" in html  # 500,000 / 1,500,000
        assert "100.0 %" in html  # Total row

    def test_122_zero_total_does_not_divide_by_zero(self):
        resumen = [{"tipo_pago": "trato", "total_pagar": 0, "jornadas": 0}]
        html = tc._summary_table_html(resumen, 0, 0)
        assert "—" in html


class TestQueryDetalleRowsColumns:
    def _rows(self, **filters):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                where, params = tc._build_detalle_filters(
                    "2026-07-01", "2026-07-31", **filters
                )
                return tc._query_detalle_rows(cur, where, params)
        finally:
            conn.close()

    def test_122_rows_include_centro_costo_nombre(self):
        rows = self._rows()
        assert rows
        assert all("centro_costo_nombre" in r for r in rows)

    def test_122_pct_pago_al_dia_y_trato_sum_to_100(self):
        """The literal spec: row total / (Al Día + Trato) — so trato rows
        and Al Día rows together must sum to 100%, not 100% each on its
        own (the old PARTITION BY tipo_pago behavior)."""
        rows = self._rows()
        total_pct = sum(
            float(r["pct_pago"] or 0)
            for r in rows
            if r["tipo_pago"] in ("trato", "Al dia", "Al día")
        )
        assert abs(total_pct - 100.0) < 0.1

    def test_122_pct_pago_matches_manual_calculation(self):
        rows = self._rows()
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                where, params = tc._build_detalle_filters("2026-07-01", "2026-07-31")
                resumen = tc._query_detalle_resumen(cur, where, params)
        finally:
            conn.close()
        al_dia_trato_total = sum(
            float(r["total_pagar"] or 0)
            for r in resumen
            if r["tipo_pago"] in ("trato", "Al dia", "Al día")
        )
        trato_row = next(r for r in rows if r["tipo_pago"] == "trato")
        expected = round(float(trato_row["costo_total"]) / al_dia_trato_total * 100, 2)
        assert abs(float(trato_row["pct_pago"]) - expected) < 0.01


class TestBuildDetalleHtmlNoChartColumns:
    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)

    def setup_method(self, monkeypatch=None):
        self._orig_header = tc._pdf_header
        tc._pdf_header = lambda title, fi, ft, filtros, *a, **kw: (
            f"<h1>{title}</h1><p>{fi}-{ft}</p>"
        )

    def teardown_method(self, monkeypatch=None):
        tc._pdf_header = self._orig_header

    def _pdf_bytes(self, resp) -> bytes:
        import asyncio

        async def _bytes():
            if getattr(resp, "body", None):
                return resp.body
            return b"".join([c async for c in resp.body_iterator])

        return asyncio.run(_bytes())

    def test_122_pdf_has_no_embedded_chart_image(self):
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
        import fitz

        doc = fitz.open(stream=body, filetype="pdf")
        images = []
        for page in doc:
            images.extend(page.get_images())
        assert len(images) == 0

    def test_122_detalle_table_columns(self):
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
        import fitz

        doc = fitz.open(stream=body, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        assert "Nombre CC" in text
        assert "Costo/hora" in text  # kept
        assert "% pago" in text  # kept
        # Header cells render as their own text line — an exact-line check
        # avoids false negatives/positives from unrelated substrings.
        lines = {ln.strip() for ln in text.splitlines()}
        assert "Horas" not in lines
        assert "Unitario" not in lines

    def test_122_resumen_table_has_percent_column(self):
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
        import fitz

        doc = fitz.open(stream=body, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        assert "%" in text


class TestCampoIsolationPctPago:
    """The pct_pago denominator is a window function over the already
    WHERE-filtered rows — filtering by campo must not pull in totals from
    another campo's Al Día/Trato rows."""

    def _rows_for_campo(self, campo: str):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                where, params = tc._build_detalle_filters(
                    "2026-07-01", "2026-07-31", campo=campo
                )
                return tc._query_detalle_rows(cur, where, params)
        finally:
            conn.close()

    def test_122_pct_pago_scoped_to_filtered_campo(self):
        rows_a = self._rows_for_campo("ISLA DE MAIPO")
        assert rows_a

        pct_a = sum(
            float(r["pct_pago"] or 0)
            for r in rows_a
            if r["tipo_pago"] in ("trato", "Al dia", "Al día")
        )
        # If the window function leaked totals from other campos, this
        # would come out far below 100% instead of summing to it.
        assert abs(pct_a - 100.0) < 0.1
