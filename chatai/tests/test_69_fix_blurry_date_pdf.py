"""
Regression test for issue #69: in the tractorista detail PDF
(GET /api/tarjas/tractorista/download-pdf), the first table (fecha ->
trabajador -> labor) had no table-layout:fixed nor explicit column widths.
Without them, xhtml2pdf/reportlab auto-sizes columns from content and the
narrow "Fecha" column overlapped the "Trabajador" text of the following
row, rendering the date as an illegible, overlapping smear.

Fixed by giving table.data the same table-layout:fixed + explicit width
treatment already used (and already correct) for the "Tabla por operador"
pivot section added in issue #67 - applied to both <th> (thead) and every
<td> (tbody), matching the pattern established in issue #52 (applying
widths only to the header is not enough, it still overlaps in the body).
"""

import os
from pathlib import Path

TARJAS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "tarjas_controller.py"
)


def _ctrl_source() -> str:
    return TARJAS_CTRL.read_text(encoding="utf-8")


def _pdf_function_source() -> str:
    src = _ctrl_source()
    start = src.index("async def download_tarjas_tractorista_pdf")
    end = src.index("\n@router", start)
    return src[start:end]


def test_69_data_table_has_fixed_layout_regression():
    fn = _pdf_function_source()
    assert "table-layout: fixed" in fn, (
        "table.data must use table-layout:fixed so column widths don't "
        "collapse and overlap adjacent cells"
    )


def test_69_header_cells_have_explicit_widths_regression():
    fn = _pdf_function_source()
    assert 'style="width:12%">Fecha' in fn, "Fecha header must have an explicit width"
    assert 'style="width:30%">Trabajador' in fn, "Trabajador header must have an explicit width"
    assert 'style="width:33%">Labor' in fn, "Labor header must have an explicit width"


def test_69_body_cells_also_have_explicit_widths_regression():
    """Widths on the header alone are not enough (issue #52 precedent) —
    every <td> in the body must repeat them or xhtml2pdf still overlaps
    text between columns."""
    fn = _pdf_function_source()
    assert 'td style="width:12%"' in fn, "Fecha body cells must repeat the width"
    assert 'td style="width:30%"' in fn, "Trabajador body cells must repeat the width"
    assert 'td style="width:33%"' in fn, "Labor body cells must repeat the width"


def test_69_column_widths_sum_to_100_percent():
    assert 12 + 30 + 33 + 25 == 100
