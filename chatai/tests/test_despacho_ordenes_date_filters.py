"""
test_despacho_ordenes_date_filters.py
--------------------------------------
Regression tests for issue #14: GET /api/despacho/ordenes must accept
fecha_inicio / fecha_termino query parameters and filter rows by date range.

These tests use static analysis of the controller source to verify the
correct SQL expression is used, consistent with the test pattern in this
codebase (no live DB required).

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_despacho_ordenes_date_filters.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

CONTROLLER_PATH = (
    Path(__file__).parent.parent / "backend" / "controllers" / "despacho_controller.py"
)


def _source() -> str:
    return CONTROLLER_PATH.read_text(encoding="utf-8")


class TestDespachoOrdenesFechaParams:
    """Issue #14 regression — get_despacho_ordenes must accept date range params."""

    def test_14_date_filters_ordenes_regression(self):
        """Regression: get_despacho_ordenes must declare fecha_inicio and fecha_termino params."""
        src = _source()

        # Locate the get_despacho_ordenes function
        func_start = src.find("async def get_despacho_ordenes(")
        assert func_start != -1, "Cannot find get_despacho_ordenes in controller"

        # Find the end of the function signature / body (next @router or end of file)
        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        assert "fecha_inicio" in func_body, (
            "get_despacho_ordenes must declare fecha_inicio parameter. "
            "Without it, the endpoint cannot filter by date range."
        )
        assert "fecha_termino" in func_body, (
            "get_despacho_ordenes must declare fecha_termino parameter. "
            "Without it, the endpoint cannot filter by date range."
        )

    def test_14_date_sql_expression(self):
        """The SQL WHERE clause must use TO_DATE(SPLIT_PART(...)) to handle MM/DD/YYYY TEXT column."""
        src = _source()

        func_start = src.find("async def get_despacho_ordenes(")
        assert func_start != -1

        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        assert "TO_DATE" in func_body.upper(), (
            "get_despacho_ordenes SQL must use TO_DATE() to cast the TEXT fecha column. "
            "Direct BETWEEN comparison on a TEXT field will silently return wrong results."
        )
        assert "BETWEEN" in func_body.upper(), (
            "get_despacho_ordenes SQL must use BETWEEN for the date range filter."
        )

    def test_14_date_validation_400(self):
        """Invalid date format must be rejected before hitting the database."""
        src = _source()

        func_start = src.find("async def get_despacho_ordenes(")
        assert func_start != -1

        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        # Must reference _DATE_RE and raise HTTPException with 400
        assert "_DATE_RE" in func_body, (
            "get_despacho_ordenes must validate date format via _DATE_RE "
            "before executing any SQL."
        )
        assert "status_code=400" in func_body, (
            "Invalid date format must return HTTP 400."
        )

    def test_14_download_also_has_date_params(self):
        """download_despacho_ordenes must also accept fecha_inicio / fecha_termino."""
        src = _source()

        func_start = src.find("async def download_despacho_ordenes(")
        assert func_start != -1, "Cannot find download_despacho_ordenes in controller"

        next_router = src.find("@router.get", func_start + 1)
        func_body = (
            src[func_start:next_router] if next_router != -1 else src[func_start:]
        )

        assert "fecha_inicio" in func_body, (
            "download_despacho_ordenes must declare fecha_inicio parameter."
        )
        assert "fecha_termino" in func_body, (
            "download_despacho_ordenes must declare fecha_termino parameter."
        )


class TestDespachoOrdenesJSDateFilter:
    """Verify the frontend JS file sends fecha_inicio / fecha_termino to the API."""

    JS_PATH = (
        Path(__file__).parent.parent.parent
        / "chatai"
        / "frontend"
        / "static"
        / "despacho_ordenes.js"
    )

    def _js(self) -> str:
        return self.JS_PATH.read_text(encoding="utf-8")

    def test_14_js_sends_fecha_inicio(self):
        """JS must include fecha_inicio in the API call params."""
        js = self._js()
        assert "fecha_inicio" in js, (
            "despacho_ordenes.js must pass fecha_inicio to /api/despacho/ordenes."
        )

    def test_14_js_sends_fecha_termino(self):
        """JS must include fecha_termino in the API call params."""
        js = self._js()
        assert "fecha_termino" in js, (
            "despacho_ordenes.js must pass fecha_termino to /api/despacho/ordenes."
        )

    def test_14_js_has_default_dates(self):
        """JS must call setDefaultDates() so the date inputs have a sensible default."""
        js = self._js()
        assert "setDefaultDates" in js, (
            "despacho_ordenes.js must call setDefaultDates() to pre-fill the date range."
        )

    def test_14_js_filter_ids_include_dates(self):
        """FILTER_IDS in JS must include fil-from and fil-to for URL sync."""
        js = self._js()
        # FILTER_IDS array must contain both date input IDs
        assert "'fil-from'" in js or '"fil-from"' in js, (
            "FILTER_IDS in despacho_ordenes.js must include 'fil-from' for URL sync."
        )
        assert "'fil-to'" in js or '"fil-to"' in js, (
            "FILTER_IDS in despacho_ordenes.js must include 'fil-to' for URL sync."
        )
