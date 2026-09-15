"""
Detalle operacional Resumen uses Total trabajado + Total Empresa, never
total_pagar (issue #160). AppSheet leaves total_pagar at 0 on many rows.

Reported URL:
  /tarjas/detalle?fil-from=2026-09-02&fil-to=2026-09-08
  &fil-contratista=MULTISERVICIOS BONHOMIA SPA&fil-empresa=ZUÑIGA

Run:
    python -m pytest chatai/tests/test_detalle_resumen_total_empresa.py -v
"""

import ast
import os
import sys
from decimal import Decimal
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc  # noqa: E402
import tarjas_empresa as te  # noqa: E402

TARJAS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "tarjas_controller.py"
)
DETAIL_HTML = (
    Path(__file__).parent.parent / "frontend" / "templates" / "tarjas_detail.html"
)
DETAIL_JS = Path(__file__).parent.parent / "frontend" / "static" / "tarjas_detail.js"

CONTRATISTA = "MULTISERVICIOS BONHOMIA SPA"
EMPRESA = "ZUÑIGA"
FECHA_INICIO = "2026-09-02"
FECHA_TERMINO = "2026-09-08"


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


def _fn_source(name: str) -> str:
    src = TARJAS_CTRL.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"function {name} not found")


def _pdf_bytes(resp) -> bytes:
    import asyncio

    async def _bytes():
        if getattr(resp, "body", None):
            return resp.body
        return b"".join([c async for c in resp.body_iterator])

    return asyncio.run(_bytes())


def _run(coro):
    import asyncio

    return asyncio.run(coro)


class TestEmpresaFactors:
    def test_al_dia_and_trato_constants(self):
        assert te.FACTOR_EMPRESA_AL_DIA == Decimal("1.50")
        assert te.FACTOR_EMPRESA_TRATO == Decimal("1.45")
        assert te.FACTOR_EMPRESA_DEFAULT == Decimal("1")

    def test_factor_al_dia_variants(self):
        assert te.factor_empresa("Al dia") == Decimal("1.50")
        assert te.factor_empresa("Al día") == Decimal("1.50")

    def test_factor_trato_variants(self):
        assert te.factor_empresa("trato") == Decimal("1.45")
        assert te.factor_empresa("Trato") == Decimal("1.45")

    def test_factor_default_does_not_invent_markup(self):
        assert te.factor_empresa("Bono") == Decimal("1")
        assert te.factor_empresa("Tractorista") == Decimal("1")
        assert te.total_empresa("Bono", 250_413) == Decimal("250413")

    def test_pago_kind_buckets(self):
        assert te.pago_kind("Al dia") == "al_dia"
        assert te.pago_kind("Al día") == "al_dia"
        assert te.pago_kind("trato") == "trato"
        assert te.pago_kind("Tractorista") == "tractorista"
        assert te.pago_kind("Bono") == "otro"

    def test_total_empresa_amounts(self):
        assert te.total_empresa("Al dia", 3_341_833) == Decimal("5012750")
        assert te.total_empresa("trato", 2_018_000) == Decimal("2926100")

    def test_markup_pct_is_the_added_percentage(self):
        assert te.markup_pct("Al dia") == Decimal("50")
        assert te.markup_pct("trato") == Decimal("45")
        assert te.markup_pct("Bono") == Decimal("0")
        assert te.format_markup(45) == "+45 %"
        assert te.format_markup(50) == "+50 %"
        assert te.format_markup(0) == "—"

    def test_no_magic_factors_outside_helper(self):
        html = DETAIL_HTML.read_text(encoding="utf-8")
        ctrl = TARJAS_CTRL.read_text(encoding="utf-8")
        for blob in (html, ctrl):
            assert "1.45" not in blob
            assert "1.50" not in blob

    def test_js_does_not_duplicate_factors(self):
        js = DETAIL_JS.read_text(encoding="utf-8")
        assert "FACTOR_EMPRESA" not in js
        assert "1.45" not in js
        assert "1.50" not in js
        assert "function enrichDetalle" in js
        assert "Number(r.total_empresa)" in js
        assert "r.recargo" in js


class TestSummaryTableHtml:
    def test_160_columns_and_values(self):
        html = tc._summary_table_html(
            [
                {
                    "tipo_pago": "Al dia",
                    "total_trabajado": 3_341_833,
                    "jornadas": 142,
                },
                {
                    "tipo_pago": "trato",
                    "total_trabajado": 2_018_000,
                    "jornadas": 72,
                },
            ],
            0,
            214,
        )
        assert "Total a pagar" not in html
        assert "Costo Empresa" in html
        assert "Recargo" in html
        assert ">%</th>" in html
        assert "$3.341.833" in html
        assert "$2.018.000" in html
        assert "$5.012.750" in html  # 3_341_833 * 1.50 rounded
        assert "$2.926.100" in html  # 2_018_000 * 1.45
        assert "$7.938.850" in html  # sum of row Costo Empresa
        assert "+45 %" in html
        assert "+50 %" in html
        assert "62.3 %" in html
        assert "37.7 %" in html
        assert "100.0 %" in html
        pct_al = 3_341_833 / 5_359_833
        pct_tr = 2_018_000 / 5_359_833
        assert abs(pct_al + pct_tr - 1) < 1e-9

    def test_160_zero_total_trabajado_no_divide_by_zero(self):
        html = tc._summary_table_html(
            [{"tipo_pago": "trato", "total_trabajado": 0, "jornadas": 0}],
            0,
            0,
        )
        assert "—" in html
        assert "100.0 %" not in html

    def test_160_footer_sums_row_empresa_not_blended_factor(self):
        rows = te.annotate_detalle_resumen(
            [
                {"tipo_pago": "Al dia", "total_trabajado": 100},
                {"tipo_pago": "trato", "total_trabajado": 200},
            ]
        )
        assert rows[0]["total_empresa"] == 150
        assert rows[0]["recargo_pct"] == 50.0
        assert rows[0]["recargo"] == "+50 %"
        assert rows[1]["total_empresa"] == 290
        assert rows[1]["recargo_pct"] == 45.0
        assert rows[1]["recargo"] == "+45 %"
        footer = sum(r["total_empresa"] for r in rows)
        assert footer == 440
        grand_trab = 300
        assert footer != float(grand_trab * te.FACTOR_EMPRESA_AL_DIA)
        assert footer != float(grand_trab * te.FACTOR_EMPRESA_TRATO)


class TestUiContract:
    def test_160_summary_helper_ignores_total_pagar(self):
        src = _fn_source("_summary_table_html")
        assert "Total a pagar" not in src
        assert "Costo Empresa" in src
        assert 'r["total_pagar"]' not in src
        api_src = _fn_source("get_tarjas_detail")
        assert "annotate_detalle_resumen" in api_src
        assert 'sum(r["total_pagar"]' not in api_src

    def test_160_web_resumen_headers(self):
        html = DETAIL_HTML.read_text(encoding="utf-8")
        summary = html.split('class="td-summary-table"')[1].split("</table>")[0]
        assert "Total a pagar" not in summary
        assert "Total trabajadores" in summary
        assert "Recargo" in summary
        assert "Costo Empresa" in summary
        assert "Jornadas" in summary
        assert ">%</th>" in html
        assert 'id="summary-empresa"' in html
        assert 'id="summary-recargo"' in html
        assert 'id="summary-pct"' in html

    def test_160_js_renders_backend_fields_and_pie_uses_trabajado(self):
        js = DETAIL_JS.read_text(encoding="utf-8")
        chart_src = js.split("function renderChart")[1].split("function renderDetail")[
            0
        ]
        assert "r.total_trabajado" in chart_src
        assert "r.total_pagar" not in chart_src
        assert "function enrichDetalle" in js
        assert "function enrichResumen" in js
        summary_src = js.split("function renderSummary")[1].split(
            "function renderChart"
        )[0]
        assert "r.total_empresa" in summary_src
        assert "r.recargo" in summary_src
        assert "r.total_pagar" not in summary_src
        assert "fmtResumenPct" in summary_src


class TestReportedWeekIntegration:
    def _ground_truth(self, conn, empresa: str):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tipo_pago,
                       COALESCE(SUM(total_trabajado), 0)
                FROM appsheet.tarjas_pagos
                WHERE fecha::date BETWEEN %s AND %s
                  AND estado = 'Aprobado'
                  AND contratista = %s
                  AND nombre_campo = %s
                GROUP BY tipo_pago
                """,
                (FECHA_INICIO, FECHA_TERMINO, CONTRATISTA, empresa),
            )
            return {r[0]: float(r[1] or 0) for r in cur.fetchall()}

    def test_160_resumen_matches_sum_trabajado_and_factors(self, conn):
        truth = self._ground_truth(conn, EMPRESA)
        assert truth, "expected Aprobado rows for the reported week"
        with conn.cursor() as cur:
            where, params = tc._build_detalle_filters(
                FECHA_INICIO,
                FECHA_TERMINO,
                contratista=CONTRATISTA,
                empresa=EMPRESA,
            )
            resumen = te.annotate_detalle_resumen(
                tc._query_detalle_resumen(cur, where, params)
            )
        by_tipo = {r["tipo_pago"]: r for r in resumen}
        for tipo, trab in truth.items():
            row = by_tipo[tipo]
            assert float(row["total_trabajado"] or 0) == trab
            assert row["total_empresa"] == float(te.total_empresa(tipo, trab))
        grand = sum(truth.values())
        assert abs(sum(float(r["pct"] or 0) for r in resumen) - 100.0) < 0.15
        assert grand > 0

    def test_160_detalle_money_from_total_trabajado(self, conn):
        with conn.cursor() as cur:
            where, params = tc._build_detalle_filters(
                FECHA_INICIO,
                FECHA_TERMINO,
                contratista=CONTRATISTA,
                empresa=EMPRESA,
            )
            rows = tc._query_detalle_rows(cur, where, params)
        assert rows
        for r in rows:
            trab = float(r["total_trabajado"] or 0)
            assert r["total_empresa"] == float(
                te.total_empresa(r["tipo_pago"], trab)
            )
            jornadas = float(r["jornadas"] or 0)
            if jornadas > 0:
                expected_u = round(trab / jornadas, 2)
                assert abs(float(r["total_unitario"] or 0) - expected_u) < 0.02
            hours = float(r.get("horas_trabajadas") or 0)
            if hours > 0:
                expected_h = round(trab / hours, 0)
                assert abs(float(r["costo_hora"] or 0) - expected_h) < 1.01

    def test_160_detalle_pct_pago_uses_total_trabajado(self, conn):
        """% del pago must follow Total trabajado, not Costo total (total_pagar)."""
        with conn.cursor() as cur:
            where, params = tc._build_detalle_filters(
                FECHA_INICIO,
                FECHA_TERMINO,
                contratista=CONTRATISTA,
                empresa=EMPRESA,
            )
            rows = tc._query_detalle_rows(cur, where, params)
        tipos = ("trato", "Al dia", "Al día")
        scoped = [r for r in rows if r["tipo_pago"] in tipos]
        grand_trab = sum(float(r["total_trabajado"] or 0) for r in scoped)
        grand_pagar = sum(float(r["costo_total"] or 0) for r in scoped)
        assert grand_trab > 0
        assert any(float(r["pct_pago"] or 0) > 0 for r in scoped)
        assert abs(sum(float(r["pct_pago"] or 0) for r in scoped) - 100.0) < 0.15
        for r in scoped:
            trab = float(r["total_trabajado"] or 0)
            if trab <= 0:
                continue
            expected = round(trab / grand_trab * 100, 2)
            assert abs(float(r["pct_pago"]) - expected) < 0.02
            if grand_pagar > 0 and abs(grand_pagar - grand_trab) > 1:
                pagar_share = round(
                    float(r["costo_total"] or 0) / grand_pagar * 100, 2
                )
                if abs(pagar_share - expected) > 0.5:
                    assert abs(float(r["pct_pago"]) - pagar_share) > 0.05

    def test_160_campo_isolation(self, conn):
        a = self._ground_truth(conn, EMPRESA)
        b = self._ground_truth(conn, "ISLA DE MAIPO")
        assert sum(a.values()) > 0
        assert sum(a.values()) != sum(b.values())

    def test_160_pdf_resumen_columns(self):
        orig = tc._pdf_header
        tc._pdf_header = lambda title, fi, ft, filtros, *a, **kw: (
            f"<h1>{title}</h1><p>{fi}-{ft}</p>"
        )
        try:
            resp = _run(
                tc.download_tarjas_detalle_pdf(
                    fecha_inicio=FECHA_INICIO,
                    fecha_termino=FECHA_TERMINO,
                    contratista=CONTRATISTA,
                    centro_costo=None,
                    tipo_pago=None,
                    labor=None,
                    campo=None,
                    empresa=EMPRESA,
                )
            )
        finally:
            tc._pdf_header = orig
        body = _pdf_bytes(resp)
        assert body[:4] == b"%PDF"
        import fitz

        doc = fitz.open(stream=body, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        assert "Resumen" in text
        assert "Costo Empresa" in text
        assert "Recargo" in text
        assert "%" in text
        assert "Total a pagar" not in text
        assert "Total trabajadores" in text
        assert "Jornadas" in text
