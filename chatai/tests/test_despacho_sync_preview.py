"""
test_despacho_sync_preview.py
------------------------------
Regression tests for issue #17: GET /api/despacho/ordenes/sync-preview

These tests use static analysis of the controller and frontend sources to
verify the feature is correctly wired up, consistent with the test pattern
used in this codebase (no live DB or BQ connection required).

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_despacho_sync_preview.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

CONTROLLER_PATH = (
    Path(__file__).parent.parent / "backend" / "controllers" / "despacho_controller.py"
)
JS_PATH = Path(__file__).parent.parent / "frontend" / "static" / "despacho_ordenes.js"
HTML_PATH = (
    Path(__file__).parent.parent / "frontend" / "templates" / "despacho_ordenes.html"
)


def _controller() -> str:
    return CONTROLLER_PATH.read_text(encoding="utf-8")


def _js() -> str:
    return JS_PATH.read_text(encoding="utf-8")


def _html() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


class TestSyncPreviewEndpoint:
    """Issue #17 regression — /api/despacho/ordenes/sync-preview endpoint."""

    def test_17_sync_preview_ordenes_regression(self):
        """Regression: sync-preview endpoint must exist in the controller."""
        src = _controller()
        assert "/api/despacho/ordenes/sync-preview" in src, (
            "Route /api/despacho/ordenes/sync-preview must be registered in "
            "despacho_controller.py (issue #17)."
        )

    def test_17_sync_preview_handler_defined(self):
        """The handler function get_despacho_ordenes_sync_preview must be defined."""
        src = _controller()
        assert "async def get_despacho_ordenes_sync_preview" in src, (
            "Handler function get_despacho_ordenes_sync_preview must be present."
        )

    def test_17_sync_preview_date_validation(self):
        """Handler must validate fecha_inicio / fecha_termino format before querying."""
        src = _controller()
        func_start = src.find("async def get_despacho_ordenes_sync_preview")
        assert func_start != -1

        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        assert "_DATE_RE.match" in func_body, (
            "sync-preview handler must validate date format using _DATE_RE "
            "before querying the database."
        )
        assert "400" in func_body, (
            "sync-preview handler must return HTTP 400 on invalid date format."
        )

    def test_17_sync_preview_bq_best_effort(self):
        """BigQuery must be called inside a try/except so BQ unavailability is non-fatal."""
        src = _controller()
        func_start = src.find("async def get_despacho_ordenes_sync_preview")
        assert func_start != -1

        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        assert "try:" in func_body, (
            "BQ query inside sync-preview must be wrapped in try/except "
            "so BigQuery unavailability does not crash the endpoint."
        )
        assert "bq_available" in func_body, (
            "sync-preview handler must return bq_available flag so the "
            "frontend can show the 'BigQuery unavailable' alert."
        )

    def test_17_sync_preview_status_classifications(self):
        """Handler must classify CCs as ok, unknown, and empty."""
        src = _controller()
        func_start = src.find("async def get_despacho_ordenes_sync_preview")
        assert func_start != -1

        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        assert '"ok"' in func_body or "'ok'" in func_body, (
            "sync-preview handler must produce status='ok' for CCs active in Odoo."
        )
        assert '"unknown"' in func_body or "'unknown'" in func_body, (
            "sync-preview handler must produce status='unknown' for unmapped CCs."
        )
        assert '"empty"' in func_body or "'empty'" in func_body, (
            "sync-preview handler must produce status='empty' for blank CC values."
        )

    def test_17_sync_preview_response_shape(self):
        """Response must include ccs list and summary counts."""
        src = _controller()
        func_start = src.find("async def get_despacho_ordenes_sync_preview")
        assert func_start != -1

        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        for key in ("ccs", "bq_available", "ok_count", "unknown_count", "empty_count"):
            assert f'"{key}"' in func_body or f"'{key}'" in func_body, (
                f"sync-preview response must include '{key}' field."
            )

    def test_17_cc_aggregation_sql(self):
        """SQL must GROUP BY centro_costo and compute num_ordenes + total_cantidad."""
        src = _controller()
        func_start = src.find("async def get_despacho_ordenes_sync_preview")
        assert func_start != -1

        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        assert "GROUP BY" in func_body.upper(), (
            "sync-preview SQL must GROUP BY centro_costo."
        )
        assert "centro_costo" in func_body, (
            "sync-preview SQL must reference centro_costo column."
        )
        assert "COUNT" in func_body.upper(), (
            "sync-preview SQL must COUNT orders per CC."
        )


class TestSyncPreviewFrontend:
    """Issue #17 regression — frontend wiring for sync preview modal."""

    def test_17_sync_preview_button_in_html(self):
        """HTML must contain the 'Verificar CCs en Odoo' button."""
        html = _html()
        assert "btn-sync-preview" in html, (
            "despacho_ordenes.html must contain button id='btn-sync-preview'."
        )
        assert "Verificar CCs en Odoo" in html, (
            "despacho_ordenes.html must contain button label 'Verificar CCs en Odoo'."
        )

    def test_17_sync_modal_in_html(self):
        """HTML must contain the sync preview modal overlay."""
        html = _html()
        assert "sync-modal" in html, (
            "despacho_ordenes.html must contain the sync preview modal (id='sync-modal')."
        )
        assert "sync-preview-tbody" in html, (
            "Modal must include tbody with id='sync-preview-tbody' for CC rows."
        )

    def test_17_sync_preview_js_function(self):
        """JS must define loadSyncPreview async function."""
        js = _js()
        assert "async function loadSyncPreview" in js, (
            "despacho_ordenes.js must define 'async function loadSyncPreview'."
        )

    def test_17_sync_preview_js_calls_endpoint(self):
        """JS loadSyncPreview must call /api/despacho/ordenes/sync-preview."""
        js = _js()
        assert "/api/despacho/ordenes/sync-preview" in js, (
            "loadSyncPreview in JS must fetch /api/despacho/ordenes/sync-preview."
        )

    def test_17_sync_preview_js_button_enabled_on_results(self):
        """JS must enable btn-sync-preview after successful fetch."""
        js = _js()
        assert "btn-sync-preview" in js, (
            "JS must reference btn-sync-preview to enable/disable it based on results."
        )

    def test_17_sync_preview_js_modal_object(self):
        """JS must define syncModal object for DOM references."""
        js = _js()
        assert "syncModal" in js, (
            "despacho_ordenes.js must define syncModal object for modal DOM access."
        )

    def test_17_sync_preview_bq_unavail_alert_in_html(self):
        """Modal must include BigQuery unavailable alert element."""
        html = _html()
        assert "sync-bq-unavail-alert" in html, (
            "Modal must contain element id='sync-bq-unavail-alert' for BQ unavailable alert."
        )

    def test_17_sync_preview_unknown_alert_in_html(self):
        """Modal must include unknown CCs alert element."""
        html = _html()
        assert "sync-unknown-alert" in html, (
            "Modal must contain element id='sync-unknown-alert' for unmapped CC alert."
        )
