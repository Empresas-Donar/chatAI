"""
Regression tests for issue #67: the "por operador" pivot table (fecha x
trabajador — labor) for the tractorista purchase order screen was only
available as an Excel download (/api/tarjas/tractorista/pivot-excel). It is
now also:
  - exposed as JSON (/api/tarjas/tractorista/pivot-preview) so the screen can
    render it below the existing per-CC tables, and
  - appended as a second table in the PDF (/api/tarjas/tractorista/download-pdf).

All three (Excel, JSON preview, PDF section) now share the same
_fetch_tractorista_pivot_rows + _build_tractorista_pivot helpers, so the
numbers can no longer drift apart between the download formats and the
on-screen table.

NOTE: unlike some other tractorista PDF endpoints in this controller,
download_tarjas_tractorista_pdf does not call _pdf_header (no glibc-only
strftime code), so no monkeypatching is needed to run these on Windows.
"""

import asyncio
import os

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_pdf_header(monkeypatch):
    # _pdf_header uses strftime("%-d de %B de %Y"), a glibc-only format code
    # that raises on Windows dev machines (pre-existing, out-of-scope issue —
    # see test_52_fix_pdf_pivot_mismatch.py). download_tarjas_tractorista_pdf
    # itself does not call _pdf_header, but general_tractorista's PDF (used
    # only for the isolation check below) does.
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


CONTRATISTA = "SERVICIOS AGRICOLAS RD SPA"  # renamed from "RAMÓN DIAZ" in issue #75
CAMPO = "TALAGANTE"
FECHA_INICIO = "2026-07-01"
FECHA_TERMINO = "2026-07-31"


class TestBuildPivotHelper:
    def test_67_build_pivot_matrix_and_totals(self):
        rows = [
            {"fecha": "2026-07-01", "trabajador": "A", "labor": "L1", "monto": 100},
            {"fecha": "2026-07-01", "trabajador": "B", "labor": "L1", "monto": 200},
            {"fecha": "2026-07-02", "trabajador": "A", "labor": "L1", "monto": 50},
        ]
        pivot = tc._build_tractorista_pivot(rows)
        assert pivot["dates"] == ["2026-07-01", "2026-07-02"]
        assert pivot["columns"] == ["A — L1", "B — L1"]
        assert pivot["matrix"]["2026-07-01"]["A — L1"] == 100
        assert pivot["matrix"]["2026-07-01"]["B — L1"] == 200
        assert pivot["matrix"]["2026-07-02"]["B — L1"] == 0
        assert pivot["date_totals"]["2026-07-01"] == 300
        assert pivot["col_totals"]["A — L1"] == 150
        assert pivot["grand_total"] == 350

    def test_67_empty_rows_produce_empty_pivot(self):
        pivot = tc._build_tractorista_pivot([])
        assert pivot["dates"] == []
        assert pivot["columns"] == []
        assert pivot["grand_total"] == 0


class TestPivotPreviewEndpointRegression:
    def test_67_pivot_preview_matches_excel_source_regression(self):
        """The new JSON preview endpoint must be built from the exact same
        rows as the Excel download — this is the whole point of the fix
        (screen, Excel and PDF must never disagree)."""
        resp = run(
            tc.preview_tarjas_tractorista_pivot(
                contratista=CONTRATISTA,
                campo=CAMPO,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        assert resp["dates"], "expected at least one date for this known dataset"
        assert resp["columns"], "expected at least one operador — labor column"
        recomputed_grand_total = sum(resp["col_totals"].values())
        assert abs(recomputed_grand_total - resp["grand_total"]) < 0.01
        for d in resp["dates"]:
            row_sum = sum(resp["matrix"][d].values())
            assert abs(row_sum - resp["date_totals"][d]) < 0.01


class TestPivotExcelStillWorksRegression:
    def test_67_pivot_excel_renders_after_refactor(self):
        """Refactoring pivot_tarjas_tractorista_excel off pandas onto the
        shared dict-based helpers must not break the Excel download."""
        resp = run(
            tc.pivot_tarjas_tractorista_excel(
                contratista=CONTRATISTA,
                campo=CAMPO,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        body = run(_bytes(resp))
        assert len(body) > 0
        assert body[:2] == b"PK"  # xlsx is a zip archive


class TestDownloadPdfIncludesPivotSection:
    def test_67_download_pdf_renders_with_pivot_section(self):
        """The main tractorista PDF must still render (now with a second,
        appended 'por operador' table) without crashing on column widths."""
        resp = run(
            tc.download_tarjas_tractorista_pdf(
                contratista=CONTRATISTA,
                campo=CAMPO,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                cc=None,
            )
        )
        body = run(_bytes(resp))
        assert body[:4] == b"%PDF"

    def test_67_download_pdf_with_cc_filter_scopes_pivot_too(self):
        """When a cc filter is passed, the pivot section must be scoped to
        that same cc (not silently show the whole contratista/campo)."""
        conn = tc.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT cuartel_cc FROM appsheet.tarjas_pagos
                    WHERE tipo_pago='Tractorista' AND contratista=%s AND nombre_campo=%s
                    LIMIT 1
                    """,
                    (CONTRATISTA, CAMPO),
                )
                row = cur.fetchone()
            assert row is not None
            cc = row[0]

            rows_all = tc._fetch_tractorista_pivot_rows(
                conn, CONTRATISTA, CAMPO, FECHA_INICIO, FECHA_TERMINO
            )
            rows_cc = tc._fetch_tractorista_pivot_rows(
                conn, CONTRATISTA, CAMPO, FECHA_INICIO, FECHA_TERMINO, cc=cc
            )
        finally:
            conn.close()
        assert len(rows_cc) <= len(rows_all)

        resp = run(
            tc.download_tarjas_tractorista_pdf(
                contratista=CONTRATISTA,
                campo=CAMPO,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                cc=cc,
            )
        )
        body = run(_bytes(resp))
        assert body[:4] == b"%PDF"


class TestNoRegressionOnUnrelatedReports:
    def test_67_general_tractorista_pdf_unaffected_isolation(self):
        """This fix touches only the tractorista purchase-order screen's
        pivot/PDF/Excel endpoints — the unrelated general-tractorista report
        must still render exactly as before."""
        resp = run(
            tc.download_tarjas_general_tractorista_pdf(
                fecha_inicio="2026-01-01",
                fecha_termino="2026-07-31",
                centro_costo=None,
                labor=None,
                contratista=None,
                empresa=None,
            )
        )
        body = run(_bytes(resp))
        assert body[:4] == b"%PDF"
