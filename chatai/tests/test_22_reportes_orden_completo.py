"""
test_22_reportes_orden_completo.py
------------------------------------
Regression tests for issue #22:
  - /reportes must include ALL contractor reports
  - Reports must appear in the same order as the navigation menu
  - Individual section PDF downloads must delegate to reports_controller (single implementation)

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_22_reportes_orden_completo.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

REPORTS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "reports_controller.py"
)
TARJAS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "tarjas_controller.py"
)

MENU_ORDER_CONTRATISTAS = [
    "detalle",
    "contratista",
    "general",
    "resumen-persona",
    "resumen-horas",
    "jornadas-trabajador",
]

MENU_ORDER_TRACTORISTAS = [
    "detalle-tractorista",
    "general-tractorista",
    "resumen-tractorista",
]

ALL_REPORT_IDS = MENU_ORDER_CONTRATISTAS + MENU_ORDER_TRACTORISTAS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reports_source() -> str:
    return REPORTS_CTRL.read_text(encoding="utf-8")


def _tarjas_source() -> str:
    return TARJAS_CTRL.read_text(encoding="utf-8")


def _extract_available_reports_ids(source: str) -> list[str]:
    """Parse the 'id': 'xxx' entries in AVAILABLE_REPORTS list order."""
    import re

    pattern = re.compile(r'"id"\s*:\s*"([^"]+)"')
    start = source.find("AVAILABLE_REPORTS = [")
    end = source.find("\n]", start) + 2
    block = source[start:end]
    return pattern.findall(block)


def _extract_report_generator_ids(source: str) -> list[str]:
    """Parse _REPORT_GENERATORS dict keys in definition order."""
    import re

    pattern = re.compile(r'"([^"]+)"\s*:')
    start = source.find("_REPORT_GENERATORS = {")
    end = source.find("\n}", start) + 2
    block = source[start:end]
    return pattern.findall(block)


# ---------------------------------------------------------------------------
# Test 1 — regression: AVAILABLE_REPORTS must include jornadas-trabajador
# ---------------------------------------------------------------------------


class TestReportesCompletoRegression:
    def test_22_reportes_include_jornadas_trabajador_regression(self):
        """Regression #22: jornadas-trabajador must be in AVAILABLE_REPORTS."""
        source = _reports_source()
        ids = _extract_available_reports_ids(source)
        assert "jornadas-trabajador" in ids, (
            "AVAILABLE_REPORTS is missing 'jornadas-trabajador' (added in issue #20 but "
            "never registered in reports_controller.py)"
        )

    def test_22_available_reports_contains_all_menu_reports(self):
        """All reports shown in the nav menu must appear in AVAILABLE_REPORTS."""
        source = _reports_source()
        ids = set(_extract_available_reports_ids(source))
        for report_id in ALL_REPORT_IDS:
            assert report_id in ids, (
                f"Report '{report_id}' is in the navigation menu but missing from AVAILABLE_REPORTS"
            )

    def test_22_contratistas_order_matches_menu(self):
        """AVAILABLE_REPORTS contratistas must appear in the same order as the nav menu."""
        source = _reports_source()
        all_ids = _extract_available_reports_ids(source)
        contratista_ids = [i for i in all_ids if i in MENU_ORDER_CONTRATISTAS]
        assert contratista_ids == MENU_ORDER_CONTRATISTAS, (
            f"Contratistas order in AVAILABLE_REPORTS: {contratista_ids}\n"
            f"Expected (menu order): {MENU_ORDER_CONTRATISTAS}"
        )

    def test_22_tractoristas_order_matches_menu(self):
        """AVAILABLE_REPORTS tractoristas must appear in the same order as the nav menu."""
        source = _reports_source()
        all_ids = _extract_available_reports_ids(source)
        tractor_ids = [i for i in all_ids if i in MENU_ORDER_TRACTORISTAS]
        assert tractor_ids == MENU_ORDER_TRACTORISTAS, (
            f"Tractoristas order in AVAILABLE_REPORTS: {tractor_ids}\n"
            f"Expected (menu order): {MENU_ORDER_TRACTORISTAS}"
        )


# ---------------------------------------------------------------------------
# Test 2 — _REPORT_GENERATORS must contain every AVAILABLE_REPORTS id
# ---------------------------------------------------------------------------


class TestReportGenerators:
    def test_22_report_generators_complete(self):
        """Every id in AVAILABLE_REPORTS must have a generator in _REPORT_GENERATORS."""
        source = _reports_source()
        available_ids = set(_extract_available_reports_ids(source))
        generator_ids = set(_extract_report_generator_ids(source))
        missing = available_ids - generator_ids
        assert not missing, (
            f"Reports in AVAILABLE_REPORTS but missing from _REPORT_GENERATORS: {missing}"
        )

    def test_22_jornadas_html_function_exists(self):
        """_html_jornadas_trabajador must be defined in reports_controller.py."""
        source = _reports_source()
        assert "def _html_jornadas_trabajador(" in source, (
            "_html_jornadas_trabajador function not found in reports_controller.py"
        )


# ---------------------------------------------------------------------------
# Test 3 — unified PDF: individual endpoints must delegate to reports_controller
# ---------------------------------------------------------------------------


class TestPdfUnification:
    def test_22_general_pdf_delegates_to_reports_controller(self):
        """download_tarjas_general_pdf must call _rc._html_general (not inline its own HTML)."""
        source = _tarjas_source()
        start = source.find("async def download_tarjas_general_pdf(")
        end = source.find("\nasync def ", start + 1)
        block = source[start:end] if end != -1 else source[start:]
        assert "_rc._html_general(" in block, (
            "download_tarjas_general_pdf does not delegate to _rc._html_general"
        )

    def test_22_detalle_pdf_delegates_to_reports_controller(self):
        """download_tarjas_detalle_pdf must call _rc._html_detalle."""
        source = _tarjas_source()
        start = source.find("async def download_tarjas_detalle_pdf(")
        end = source.find("\nasync def ", start + 1)
        block = source[start:end] if end != -1 else source[start:]
        assert "_rc._html_detalle(" in block, (
            "download_tarjas_detalle_pdf does not delegate to _rc._html_detalle"
        )

    def test_22_contratista_pdf_delegates_to_reports_controller(self):
        """download_tarjas_contratista_pdf must call _rc._html_contratista."""
        source = _tarjas_source()
        start = source.find("async def download_tarjas_contratista_pdf(")
        end = source.find("\nasync def ", start + 1)
        block = source[start:end] if end != -1 else source[start:]
        assert "_rc._html_contratista(" in block, (
            "download_tarjas_contratista_pdf does not delegate to _rc._html_contratista"
        )

    def test_22_resumen_persona_pdf_delegates_to_reports_controller(self):
        """download_tarjas_resumen_persona_pdf must call _rc._html_resumen_persona."""
        source = _tarjas_source()
        start = source.find("async def download_tarjas_resumen_persona_pdf(")
        end = source.find("\nasync def ", start + 1)
        block = source[start:end] if end != -1 else source[start:]
        assert "_rc._html_resumen_persona(" in block, (
            "download_tarjas_resumen_persona_pdf does not delegate to _rc._html_resumen_persona"
        )

    def test_22_resumen_horas_pdf_delegates_to_reports_controller(self):
        """download_tarjas_resumen_horas_pdf must call _rc._html_resumen_horas."""
        source = _tarjas_source()
        start = source.find("async def download_tarjas_resumen_horas_pdf(")
        end = source.find("\nasync def ", start + 1)
        block = source[start:end] if end != -1 else source[start:]
        assert "_rc._html_resumen_horas(" in block, (
            "download_tarjas_resumen_horas_pdf does not delegate to _rc._html_resumen_horas"
        )

    def test_22_jornadas_trabajador_pdf_delegates_to_reports_controller(self):
        """download_tarjas_jornadas_trabajador_pdf must call _rc._html_jornadas_trabajador."""
        source = _tarjas_source()
        start = source.find("async def download_tarjas_jornadas_trabajador_pdf(")
        end = source.find("\nasync def ", start + 1)
        block = source[start:end] if end != -1 else source[start:]
        assert "_rc._html_jornadas_trabajador(" in block, (
            "download_tarjas_jornadas_trabajador_pdf does not delegate to _rc._html_jornadas_trabajador"
        )

    def test_22_resumen_tractorista_pdf_endpoint_exists(self):
        """resumen-persona-tractorista must have a PDF download endpoint in tarjas_controller."""
        source = _tarjas_source()
        assert "resumen-persona-tractorista/download-pdf" in source, (
            "Missing PDF download endpoint for resumen-persona-tractorista in tarjas_controller.py"
        )

    def test_22_tractorista_pdf_uses_shared_tarjas_builder(self):
        """download_tarjas_resumen_persona_tractorista_pdf must call the
        same builder the bulk /reportes PDF uses (issue #116)."""
        source = _tarjas_source()
        start = source.find(
            "async def download_tarjas_resumen_persona_tractorista_pdf("
        )
        end = source.find("\nasync def ", start + 1)
        block = source[start:end] if end != -1 else source[start:]
        assert "_build_resumen_persona_tractorista_html(" in block, (
            "download_tarjas_resumen_persona_tractorista_pdf does not use "
            "_build_resumen_persona_tractorista_html"
        )
