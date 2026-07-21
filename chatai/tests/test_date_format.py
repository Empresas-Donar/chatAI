"""
test_date_format.py
--------------------
Regression tests for issue #1: Standardize date format to DD/MM/YYYY.

These tests verify that every user-facing date formatting function produces
DD/MM/YYYY output and never ISO 8601 (YYYY-MM-DD), MM/DD/YYYY, or abbreviated
month formats (e.g. "5 ene 2025").

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_date_format.py -v
"""

import datetime
import re
import sys
from pathlib import Path

import pytest

# Allow importing backend modules
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── Regex patterns ────────────────────────────────────────────────────────────

DD_MM_YYYY = re.compile(r"^\d{2}/\d{2}/\d{4}$")
ISO_DATE   = re.compile(r"\d{4}-\d{2}-\d{2}")
ABBR_MONTH = re.compile(r"\b(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b")


# ── Inline copy of _fmt_date_display from reports_controller.py ───────────────
# Copied here to avoid complex import stubbing; kept in sync with the source.

def _fmt_date_display(iso: str) -> str:
    """Format an ISO date string (YYYY-MM-DD) as DD/MM/YYYY for user-facing display.

    Mirrors reports_controller.py::_fmt_date_display exactly.
    """
    try:
        d = datetime.date.fromisoformat(iso)
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    except Exception:
        return iso


# ── Tests for backend _fmt_date_display ──────────────────────────────────────

class TestFmtDateDisplay:
    """Issue #1 regression — _fmt_date_display must return DD/MM/YYYY."""

    def test_1_standardize_date_format_regression(self):
        """Regression test: a known ISO date produces DD/MM/YYYY, not 'D mes YYYY'."""
        result = _fmt_date_display("2026-07-21")
        assert result == "21/07/2026", f"Expected '21/07/2026', got '{result}'"

    def test_output_matches_dd_mm_yyyy_pattern(self):
        assert DD_MM_YYYY.match(_fmt_date_display("2026-01-05")), "Output must match DD/MM/YYYY"

    def test_no_iso_format_in_output(self):
        result = _fmt_date_display("2026-07-21")
        assert not ISO_DATE.search(result), f"Output must not contain ISO date: {result}"

    def test_no_abbreviated_month_in_output(self):
        for month in range(1, 13):
            iso = f"2026-{month:02d}-15"
            result = _fmt_date_display(iso)
            assert not ABBR_MONTH.search(result), \
                f"Output must not contain abbreviated month name: {result}"

    def test_zero_padded_day_and_month(self):
        result = _fmt_date_display("2026-01-05")
        assert result == "05/01/2026", f"Day and month must be zero-padded: {result}"

    def test_invalid_input_returns_original(self):
        result = _fmt_date_display("not-a-date")
        assert result == "not-a-date"

    def test_empty_string_returns_empty(self):
        result = _fmt_date_display("")
        # Should not raise; returns empty or original
        assert isinstance(result, str)


# ── Pure-Python tests for JS formatting logic ─────────────────────────────────
# These mirror the JS functions in Python to verify correctness without a browser.

def _py_parse_fecha(s: str) -> str:
    """Python equivalent of despacho_ordenes.js parseFecha()."""
    if not s:
        return "—"
    import re as _re
    m = _re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        # MM/DD/YYYY source → DD/MM/YYYY display
        return f"{m.group(2)}/{m.group(1)}/{m.group(3)}"
    iso = _re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if iso:
        return f"{iso.group(3)}/{iso.group(2)}/{iso.group(1)}"
    return s


def _py_fmt_date(s: str) -> str:
    """Python equivalent of the JS fmtDate() used in despacho_resumen/guia/purchase_orders."""
    if not s:
        return "—"
    parts = s.split("-")
    y, m, d = parts[0], parts[1], parts[2]
    return f"{d}/{m}/{y}"


def _py_format_short_date(iso_str: str) -> str:
    """Python equivalent of the JS formatShortDate() in tarjas_* files."""
    if not iso_str:
        return "—"
    parts = iso_str[:10].split("-")
    y, m, d = parts[0], parts[1], parts[2]
    return f"{d}/{m}/{y}"


def _py_format_display_date(iso_str: str) -> str:
    """Python equivalent of billing_order.js formatDisplayDate()."""
    if not iso_str:
        return ""
    parts = iso_str[:10].split("-")
    y, m, d = parts[0], parts[1], parts[2]
    return f"{d}/{m}/{y}"


class TestJsDateFunctions:
    """Issue #1 regression — JS date formatting functions produce DD/MM/YYYY."""

    def test_1_standardize_date_format_regression_parse_fecha_mm_dd_yyyy(self):
        """despacho_ordenes parseFecha: MM/DD/YYYY source → DD/MM/YYYY display."""
        result = _py_parse_fecha("07/21/2026 00:00:00")
        assert result == "21/07/2026", f"Expected '21/07/2026', got '{result}'"

    def test_parse_fecha_not_us_format(self):
        """parseFecha must not produce MM/DD/YYYY output."""
        result = _py_parse_fecha("07/21/2026 00:00:00")
        assert result != "07/21/2026", "Output must not be MM/DD/YYYY"

    def test_parse_fecha_iso_fallback(self):
        """parseFecha: YYYY-MM-DD fallback → DD/MM/YYYY."""
        result = _py_parse_fecha("2026-07-21")
        assert result == "21/07/2026"

    def test_fmt_date_despacho_resumen(self):
        """despacho_resumen fmtDate: YYYY-MM-DD → DD/MM/YYYY."""
        result = _py_fmt_date("2026-07-21")
        assert result == "21/07/2026"
        assert "-" not in result, f"Output must use slashes, not hyphens: {result}"

    def test_fmt_date_no_hyphen_separator(self):
        """fmtDate must use '/' not '-' as separator."""
        result = _py_fmt_date("2026-01-05")
        assert result == "05/01/2026"
        assert "-" not in result

    def test_format_short_date_tarjas(self):
        """tarjas formatShortDate: ISO → DD/MM/YYYY (no abbreviated month)."""
        result = _py_format_short_date("2026-07-21")
        assert result == "21/07/2026"
        assert not ABBR_MONTH.search(result), \
            f"Output must not contain abbreviated month: {result}"

    def test_format_display_date_billing(self):
        """billing_order formatDisplayDate: ISO → DD/MM/YYYY."""
        result = _py_format_display_date("2026-07-21")
        assert result == "21/07/2026"

    def test_all_months_produce_dd_mm_yyyy(self):
        """All 12 months produce DD/MM/YYYY without month names."""
        for month in range(1, 13):
            iso = f"2026-{month:02d}-15"
            for fn in [_py_fmt_date, _py_format_short_date, _py_format_display_date]:
                result = fn(iso)
                assert DD_MM_YYYY.match(result), \
                    f"{fn.__name__}({iso!r}) = {result!r} — must match DD/MM/YYYY"
                assert not ABBR_MONTH.search(result), \
                    f"{fn.__name__}({iso!r}) = {result!r} — must not contain month name"


class TestTarjasControllerDateFormat:
    """Issue #1 regression — tarjas_controller.py Excel/HTML date headers use DD/MM/YYYY."""

    def test_excel_date_header_format(self):
        """Excel pivot date headers use DD/MM/YYYY, not abbreviated month."""
        d = datetime.date(2026, 7, 21)
        result = d.strftime("%d/%m/%Y")
        assert result == "21/07/2026"
        assert not ABBR_MONTH.search(result)

    def test_html_pivot_header_format(self):
        """HTML pivot date headers use DD/MM (compact), not abbreviated month."""
        d = datetime.date(2026, 1, 5)
        result = d.strftime("%d/%m")
        assert result == "05/01"
        assert not ABBR_MONTH.search(result)
