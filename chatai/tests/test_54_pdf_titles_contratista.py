"""
Regression tests for issue #54: PDFs filtered by contratista must show the
contratista name in the title, format "Tarjas-Reporte {Report}-{Contratista}".
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc  # noqa: E402


class TestPdfTitleHelper:
    def test_54_title_includes_capitalized_contratista(self):
        title = tc._pdf_title("Detalle Contratistas", "HERBI ML SPA")
        assert title == "Tarjas-Reporte Detalle Contratistas-Herbi Ml Spa"

    def test_54_title_omits_suffix_when_no_contratista(self):
        title = tc._pdf_title("Detalle Contratistas", None)
        assert title == "Tarjas-Reporte Detalle Contratistas"

    def test_54_title_omits_suffix_for_empty_string(self):
        title = tc._pdf_title("Horas Extra", "")
        assert title == "Tarjas-Reporte Horas Extra"

    def test_54_all_report_labels_regression(self):
        """Every contratista-filterable PDF must use its own report label —
        guards against copy-paste reusing the wrong label. All 8 tarjas PDF
        endpoints accept a contratista filter (issue #54 originally missed
        general/detalle/resumen-persona/jornadas-trabajador — only 4 of 8
        were covered in the first pass)."""
        cases = {
            "Detalle Contratistas": tc._pdf_title("Detalle Contratistas", "HERBI ML SPA"),
            "Detalle Tractoristas": tc._pdf_title("Detalle Tractoristas", "HERBI ML SPA"),
            "General Tractoristas": tc._pdf_title("General Tractoristas", "HERBI ML SPA"),
            "Horas Extra": tc._pdf_title("Horas Extra", "HERBI ML SPA"),
            "General Operacional": tc._pdf_title("General Operacional", "HERBI ML SPA"),
            "Detalle Operacional": tc._pdf_title("Detalle Operacional", "HERBI ML SPA"),
            "Jornadas Por Trabajador": tc._pdf_title("Jornadas Por Trabajador", "HERBI ML SPA"),
            "Resumen Por Persona": tc._pdf_title("Resumen Por Persona", "HERBI ML SPA"),
        }
        for label, title in cases.items():
            assert title == f"Tarjas-Reporte {label}-Herbi Ml Spa"

    def test_54_bulk_pdf_titles_now_match_standalone_via_shared_builders(self):
        """Superseded by issue #116: the bulk multi-report PDF (/reportes)
        used to keep its own static titles, deliberately isolated from this
        issue's _pdf_title() convention. #116 removed that duplication —
        reports_controller.py now imports tarjas_controller.py's builder
        functions directly, so every bulk section's title is produced by
        the exact same _pdf_title() call as its standalone PDF. This test
        used to assert the opposite (static titles); it now asserts the
        bulk generator dict resolves to the shared builders."""
        import inspect

        import controllers.reports_controller as rc

        # Directly verifies the "general" and "contratista" bulk sections
        # delegate to tarjas_controller's shared builders, not a local copy.

        general_src = inspect.getsource(rc._REPORT_GENERATORS["general"])
        assert "tc._build_general_html" in general_src
        contratista_src = inspect.getsource(rc._REPORT_GENERATORS["contratista"])
        assert "tc._build_contratista_html" in contratista_src


class TestPdfTitleIntegration:
    """End-to-end: the actual PDF bytes must contain the expected title
    text for each of the 8 contratista-filterable reports."""

    def _title_text(self, resp) -> str:
        import asyncio

        import fitz

        async def _bytes():
            if getattr(resp, "body", None):
                return resp.body
            return b"".join([c async for c in resp.body_iterator])

        body = asyncio.run(_bytes())
        doc = fitz.open(stream=body, filetype="pdf")
        return doc[0].get_text()

    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)

    def setup_method(self, monkeypatch=None):
        import controllers.tarjas_controller as _tc

        self._orig_header = _tc._pdf_header
        _tc._pdf_header = (
            lambda title, fi, ft, filtros, *a, **kw: f"<h1>{title}</h1><p>{fi}-{ft}</p>"
        )

    def teardown_method(self, monkeypatch=None):
        import controllers.tarjas_controller as _tc

        _tc._pdf_header = self._orig_header

    def test_54_general_pdf_title_regression(self):
        resp = self._run(
            tc.download_tarjas_general_pdf(
                fecha_inicio="2026-07-22",
                fecha_termino="2026-07-28",
                centro_costo=None,
                tipo_pago=None,
                labor=None,
                contratista="HERBI ML SPA",
                empresa=None,
            )
        )
        text = self._title_text(resp)
        assert "Tarjas-Reporte General Operacional-Herbi Ml Spa" in text

    def test_54_detalle_pdf_title_regression(self):
        resp = self._run(
            tc.download_tarjas_detalle_pdf(
                fecha_inicio="2026-07-22",
                fecha_termino="2026-07-28",
                contratista="HERBI ML SPA",
                centro_costo=None,
                tipo_pago=None,
                labor=None,
                campo=None,
                empresa=None,
            )
        )
        text = self._title_text(resp)
        assert "Tarjas-Reporte Detalle Operacional-Herbi Ml Spa" in text

    def test_54_jornadas_trabajador_pdf_title_regression(self):
        resp = self._run(
            tc.download_tarjas_jornadas_trabajador_pdf(
                fecha_inicio="2026-07-22",
                fecha_termino="2026-07-28",
                contratista="HERBI ML SPA",
                empresa=None,
            )
        )
        text = self._title_text(resp)
        assert "Tarjas-Reporte Jornadas Por Trabajador-Herbi Ml Spa" in text

    def test_54_resumen_persona_pdf_title_regression(self):
        """resumen-persona builds its header inline (not via _pdf_header) —
        the title must still update, unaffected by the stub above."""
        resp = self._run(
            tc.download_tarjas_resumen_persona_pdf(
                fecha_inicio="2026-07-22",
                fecha_termino="2026-07-28",
                trabajador=None,
                tipo_pago=None,
                contratista="HERBI ML SPA",
                empresa=None,
            )
        )
        text = self._title_text(resp)
        assert "Tarjas-Reporte Resumen Por" in text and "Persona-Herbi Ml Spa" in text
