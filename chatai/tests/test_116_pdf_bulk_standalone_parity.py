"""
Regression tests for issue #116: users reported that several reports in the
bulk /reportes PDF (Hora Ponderada 9h, Detalle Operacional, Bonos
Mensuales, ...) rendered differently from their standalone PDF downloads —
different header/title format, missing highlighting, different date
formatting in the "Desde"/"Hasta" chips, and outright different table
structures for some reports (e.g. general-tractorista queried completely
different columns in each version).

Root cause: reports_controller.py re-implemented each report's HTML from
scratch instead of sharing code with tarjas_controller.py's standalone PDF
endpoints, so every fix or tweak made to one side silently didn't apply to
the other (issues #108/#112 already show this happening once).

Fix: tarjas_controller.py's standalone PDF endpoints now delegate their
HTML body to a `_build_<report>_html()` function; reports_controller.py's
bulk PDF imports and calls those same functions instead of keeping its own
copies. This file locks that sharing in place — for every report that has
both a standalone PDF and a bulk section, the two must produce identical
HTML for the same filters. Also fixes a real bug found along the way:
_pdf_header() showed the Desde/Hasta date chips as raw ISO strings
(e.g. "2026-07-01"), violating the project's "DD/MM/YYYY sin excepciones"
convention.

"resumen-tractorista" is the one report registered in the bulk PDF with no
standalone PDF counterpart (only screen + Excel exist) — nothing to share
code with, so it keeps its own implementation and is tested separately.
"""

import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.reports_controller as rc
import controllers.tarjas_controller as tc

FECHA_INICIO = "2026-07-01"
FECHA_TERMINO = "2026-07-15"
CONTRATISTA = "HERBI ML SPA"

# report id -> the tarjas_controller builder reports_controller.py must
# delegate to for that id (mirrors _REPORT_GENERATORS' wiring).
BUILDER_MAP = {
    "detalle": tc._build_detalle_html,
    "contratista": tc._build_contratista_html,
    "general": tc._build_general_html,
    "resumen-persona": tc._build_resumen_persona_html,
    "resumen-horas": tc._build_resumen_horas_html,
    "jornadas-trabajador": tc._build_jornadas_trabajador_html,
    "bono-mensual": tc._build_bono_mensual_html,
    "hora-ponderada-9h": tc._build_hora_ponderada_html,
    "detalle-tractorista": tc._build_detalle_tractorista_html,
    "general-tractorista": tc._build_general_tractorista_html,
}


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
    # _pdf_header() uses strftime("%-d de %B de %Y"), a Linux/macOS-only
    # directive that raises ValueError on Windows — unrelated to this issue.
    orig = tc._pdf_header
    tc._pdf_header = lambda title, fi, ft, filtros, *a, **kw: (
        f"<h1>{title}</h1><p>{tc._fmt_date_slash(fi)}-{tc._fmt_date_slash(ft)}</p>"
    )
    yield
    tc._pdf_header = orig


class TestAllReportsDelegateToSharedBuilder:
    @pytest.mark.parametrize("report_id", sorted(BUILDER_MAP.keys()))
    def test_116_bulk_section_matches_standalone_builder_regression(
        self, conn, report_id
    ):
        """The exact same guarantee, for every report that has a standalone
        PDF: the bulk /reportes section and the standalone builder produce
        byte-identical HTML for the same filters."""
        builder = BUILDER_MAP[report_id]
        with conn.cursor() as cur:
            expected = builder(
                cur, FECHA_INICIO, FECHA_TERMINO, contratista=CONTRATISTA, empresa=None
            )
        with conn.cursor() as cur:
            actual = rc._REPORT_GENERATORS[report_id](
                cur, FECHA_INICIO, FECHA_TERMINO, None, CONTRATISTA
            )
        assert actual == expected

    def test_116_all_ten_reports_with_standalone_pdfs_covered(self):
        """Guards against a report being added to _REPORT_GENERATORS without
        also being added to BUILDER_MAP above (i.e. without verifying it
        shares code) — the only allowed gap is resumen-tractorista, which
        has no standalone PDF to share with."""
        bulk_ids = set(rc._REPORT_GENERATORS.keys())
        assert bulk_ids - set(BUILDER_MAP.keys()) == {"resumen-tractorista"}


class TestDateFormatBugFix:
    def test_116_fmt_date_slash_produces_ddmmyyyy(self):
        """_fmt_date_slash is what _pdf_header's Desde/Hasta chips now use
        instead of the raw ISO string, per CLAUDE.md's "Fechas en UI:
        DD/MM/YYYY — sin excepciones"."""
        assert tc._fmt_date_slash("2026-07-01") == "01/07/2026"
        assert tc._fmt_date_slash("2026-12-31") == "31/12/2026"

    def test_116_pdf_header_source_uses_fmt_date_slash_for_chips(self):
        """Structural check that _pdf_header's Desde/Hasta chips call
        _fmt_date_slash (not the raw fecha_inicio/fecha_termino strings) —
        avoids depending on datetime.strftime('%-d ...'), which raises on
        Windows and would make this test unrunnable outside Linux/macOS."""
        import inspect

        src = inspect.getsource(_ORIGINAL_PDF_HEADER)
        assert "_fmt_date_slash(fecha_inicio)" in src
        assert "_fmt_date_slash(fecha_termino)" in src


_ORIGINAL_PDF_HEADER = tc._pdf_header


class TestResumenTractoristaStillWorks:
    """The one bulk report without a standalone PDF — verify it still
    renders and uses the shared _pdf_header/_pdf_title, even though it
    can't share a builder function with anything."""

    def test_116_resumen_tractorista_uses_shared_pdf_title_format(self, conn):
        with conn.cursor() as cur:
            html = rc._REPORT_GENERATORS["resumen-tractorista"](
                cur, FECHA_INICIO, FECHA_TERMINO, None, CONTRATISTA
            )
        assert "Tarjas-Reporte Resumen Tractorista-Herbi Ml Spa" in html
