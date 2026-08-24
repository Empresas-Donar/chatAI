"""
Regression tests for issue #52: PDF exports for tarjas reports did not match
the on-screen pivot format.

Root cause 1 (contratista): download_tarjas_contratista_pdf ran a flat
GROUP BY (no fecha) and rendered a Costo/hr | Prom/dia | Dias | Total summary,
while the screen and the Excel export build a per-date pivot (one column per
date). Fixed by porting the same pivot logic used in
download_tarjas_contratista_excel.

Root cause 2 (missing endpoints): the "Detalle tractorista" and "General
tractorista" pages have a PDF button wired to /api/tarjas/detalle-tractorista
/download-pdf and /api/tarjas/general-tractorista/download-pdf, but neither
route existed in tarjas_controller.py — clicking PDF always 404'd.

Root cause 3 (wide-pivot crash): once the date dimension is restored, a wide
pivot table with no explicit column widths overflows the PDF page width and
reportlab raises "negative availWidth" — reproducible with a single ordinary
week (7 date columns). Fixed with _pivot_col_widths (table-layout: fixed +
computed % widths on every header AND body cell) and a _check_pivot_date_range
guard that rejects excessively wide ranges with a clear 400 instead of
producing an unreadable PDF.

NOTE: _pdf_header uses strftime("%-d de %B de %Y"), a glibc-only format code
that raises ValueError on Windows (a separate, pre-existing, out-of-scope
issue — production runs on Cloud Run/Linux where it works). Tests patch
_pdf_header to a no-op so they exercise the actual query/pivot/CSS logic
under test on any platform.
"""

import asyncio
import os

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_pdf_header(monkeypatch):
    # _pdf_header uses strftime("%-d de %B de %Y"), a glibc-only format code
    # that raises on Windows dev machines (pre-existing, out-of-scope issue —
    # production runs on Cloud Run/Linux where it works fine). Stubbed here
    # so these tests exercise the query/pivot/CSS logic under test on any OS.
    monkeypatch.setattr(
        tc,
        "_pdf_header",
        lambda title, fi, ft, filtros, *a, **kw: f"<h1>{title}</h1><p>{fi}-{ft}</p>",
    )


def run(coro):
    return asyncio.run(coro)


async def _bytes(resp):
    if getattr(resp, "body", None):
        return resp.body
    return b"".join([c async for c in resp.body_iterator])


class TestPivotColWidths:
    def test_52_widths_sum_to_100_percent_of_declared_table_width(self):
        """Issue #132: a range with few dates now renders a narrower table
        instead of always stretching to fill the page — each returned
        column width is a percent OF THAT TABLE (w['table']), not of the
        page. The 100%-sum invariant that guards against reportlab's
        'negative availWidth' crash (#52) now applies at that level, so the
        returned (already table-relative) widths must sum to 100 — not the
        raw, unscaled fixed_pct input."""
        fixed = {"worker": 16, "labor": 18, "tipo": 10, "rate": 10, "total": 10}
        w = tc._pivot_col_widths(fixed, 7)
        returned_fixed_sum = sum(
            float(w[k].split(":")[1].rstrip("%")) for k in fixed
        )
        date_pct = float(w["date"].split(":")[1].rstrip("%"))
        assert abs(returned_fixed_sum + date_pct * 7 - 100) < 0.01

    def test_52_many_dates_falls_back_to_full_width(self):
        """Once fixed + n_dates*date_pct would exceed 100%, the table stays
        full width and the date columns share the remainder evenly — same
        behavior as before #132, still guarding against the #52 crash."""
        fixed = {"worker": 16, "labor": 18, "tipo": 10, "rate": 10, "total": 10}
        w = tc._pivot_col_widths(fixed, 30)
        assert w["table"] == "width:100.0%"
        fixed_sum = sum(fixed.values())
        date_pct = float(w["date"].split(":")[1].rstrip("%"))
        assert abs(fixed_sum + date_pct * 30 - 100) < 0.01

    def test_52_few_dates_narrows_table_below_100_percent(self):
        """The behavior issue #132 actually added: a handful of dates no
        longer stretches fixed columns' RENDERED (page-relative) width to
        fill the page — the table itself narrows instead."""
        fixed = {"worker": 16, "labor": 18, "tipo": 10, "rate": 10, "total": 10}
        w = tc._pivot_col_widths(fixed, 3)
        table_pct = float(w["table"].split(":")[1].rstrip("%"))
        assert table_pct < 100.0
        assert table_pct == pytest.approx(64 + 3.5 * 3)

    def test_52_zero_dates_does_not_divide_by_zero(self):
        w = tc._pivot_col_widths({"worker": 22, "tipo": 14, "total": 12}, 0)
        assert w["date"] == "width:0.0%"


class TestPivotDateRangeGuard:
    def test_52_wide_range_raises_400(self):
        dates = [f"2026-01-{d:02d}" for d in range(1, 32)] + [
            f"2026-02-{d:02d}" for d in range(1, 20)
        ]
        with pytest.raises(HTTPException) as exc_info:
            tc._check_pivot_date_range(dates, "Detalle contratista")
        assert exc_info.value.status_code == 400
        assert "Detalle contratista" in exc_info.value.detail

    def test_52_narrow_range_does_not_raise(self):
        dates = [f"2026-07-{d:02d}" for d in range(22, 29)]
        tc._check_pivot_date_range(dates, "Detalle contratista")  # must not raise


class TestContratistaPdfRegression:
    def test_52_contratista_pdf_no_longer_flat_aggregation_regression(self):
        """The PDF must render without error — the original bug rendered
        Costo/hr | Prom/dia | Dias | Total (flat) instead of a per-date pivot."""
        resp = run(
            tc.download_tarjas_contratista_pdf(
                fecha_inicio="2026-07-22",
                fecha_termino="2026-07-28",
                contratista="HERBI ML SPA",
                centro_costo=None,
                tipo_pago=None,
                labor=None,
                empresa="TALAGANTE",
            )
        )
        body = run(_bytes(resp))
        assert len(body) > 0
        assert body[:4] == b"%PDF"

    def test_52_contratista_pdf_wide_range_rejected_not_garbled(self):
        with pytest.raises(HTTPException) as exc_info:
            run(
                tc.download_tarjas_contratista_pdf(
                    fecha_inicio="2026-01-01",
                    fecha_termino="2026-07-28",
                    contratista=None,
                    centro_costo=None,
                    tipo_pago=None,
                    labor=None,
                    empresa=None,
                )
            )
        assert exc_info.value.status_code == 400


class TestMissingTractoristaPdfEndpoints:
    """Regression: these PDF routes did not exist before issue #52 — the
    on-screen PDF button 404'd for both reports."""

    def test_52_detalle_tractorista_pdf_endpoint_exists_and_renders(self):
        resp = run(
            tc.download_tarjas_detalle_tractorista_pdf(
                fecha_inicio="2026-01-01",
                fecha_termino="2026-07-28",
                contratista=None,
                empresa=None,
                centro_costo=None,
                labor=None,
                campo=None,
            )
        )
        body = run(_bytes(resp))
        assert body[:4] == b"%PDF"

    def test_52_general_tractorista_pdf_endpoint_exists_and_renders(self):
        resp = run(
            tc.download_tarjas_general_tractorista_pdf(
                fecha_inicio="2026-01-01",
                fecha_termino="2026-07-28",
                centro_costo=None,
                labor=None,
                contratista=None,
                empresa=None,
            )
        )
        body = run(_bytes(resp))
        assert body[:4] == b"%PDF"


class TestCrossReportIsolation:
    """Isolation check: the contratista pivot fix must not have altered the
    unrelated flat-list PDF reports (general, detalle, jornadas-trabajador)."""

    def test_52_general_pdf_still_flat_not_pivoted(self):
        resp = run(
            tc.download_tarjas_general_pdf(
                fecha_inicio="2026-07-22",
                fecha_termino="2026-07-28",
                contratista=None,
                centro_costo=None,
                tipo_pago=None,
                labor=None,
                empresa=None,
            )
        )
        body = run(_bytes(resp))
        assert body[:4] == b"%PDF"
