"""
Detalle operacional adds a "Total trabajado" column (SUM(total_trabajado)
from tarjas_pagos, Aprobado) so the cuadrilla figure is visible even when
AppSheet leaves total_pagar at 0.

Reported case: HERBI ML SPA · TALAGANTE · 2026-08-26–2026-09-01
  Total a pagar / Costo total = $1.131.000 (total_pagar)
  Total trabajado             = $2.219.000 (total_trabajado)

Run:
    python -m pytest chatai/tests/test_detalle_operacional_total_trabajado.py -v
"""

import ast
import os
import sys
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc  # noqa: E402

TARJAS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "tarjas_controller.py"
)
DETAIL_HTML = (
    Path(__file__).parent.parent / "frontend" / "templates" / "tarjas_detail.html"
)
DETAIL_JS = Path(__file__).parent.parent / "frontend" / "static" / "tarjas_detail.js"

CONTRATISTA = "HERBI ML SPA"
EMPRESA = "TALAGANTE"
FECHA_INICIO = "2026-08-26"
FECHA_TERMINO = "2026-09-01"
EXPECTED_PAGAR = 1_131_000
EXPECTED_TRABAJADO = 2_219_000


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


def test_detalle_queries_both_amounts_from_pagos():
    rows_src = _fn_source("_query_detalle_rows")
    resumen_src = _fn_source("_query_detalle_resumen")
    for src in (rows_src, resumen_src):
        assert "tarjas_pagos" in src
        assert "total_trabajado" in src
        assert "tarjas_reporte" not in src
        assert "total_labor" not in src
    assert "total_pagar" in rows_src
    assert "costo_total" in rows_src


def test_detalle_ui_has_total_trabajado_column():
    html = DETAIL_HTML.read_text(encoding="utf-8")
    assert html.count("Total trabajado") >= 2  # resumen + detalle headers
    assert 'id="detail-tfoot"' in html
    js = DETAIL_JS.read_text(encoding="utf-8")
    assert "total_trabajado" in js
    assert "summary-trabajado" in js
    assert "detail-tfoot" in js
    assert "fmtCLP.format(sumTrab)" in js


def test_detalle_ui_shows_centro_costo_nombre():
    html = DETAIL_HTML.read_text(encoding="utf-8")
    assert "<th>Nombre CC</th>" in html
    js = DETAIL_JS.read_text(encoding="utf-8")
    assert "centro_costo_nombre" in js
    assert 'colspan="4"' in js
    excel_src = _fn_source("download_tarjas_detalle_excel")
    assert '"Nombre CC"' in excel_src
    assert 'r["centro_costo_nombre"]' in excel_src


def test_detalle_pdf_html_has_detail_tfoot():
    src = _fn_source("_build_detalle_html")
    assert "foot_html" in src
    assert "<tfoot>" in src
    assert "Total trabajado" in src


def test_detalle_pdf_summary_has_trabajado_column():
    html = tc._summary_table_html(
        [
            {"tipo_pago": "trato", "total_pagar": 1000000, "total_trabajado": 800000, "jornadas": 10},
            {"tipo_pago": "Al dia", "total_pagar": 500000, "total_trabajado": 400000, "jornadas": 5},
        ],
        1500000,
        15,
    )
    assert "Total trabajado" in html
    assert "$800.000" in html
    assert "$1.200.000" in html  # footer trabajado
    assert "Total a pagar" in html


def test_detalle_herbi_talagante_week_both_totals(conn):
    with conn.cursor() as cur:
        where, params = tc._build_detalle_filters(
            FECHA_INICIO,
            FECHA_TERMINO,
            contratista=CONTRATISTA,
            empresa=EMPRESA,
        )
        resumen = tc._query_detalle_resumen(cur, where, params)
        rows = tc._query_detalle_rows(cur, where, params)

    pagar = sum(float(r["total_pagar"] or 0) for r in resumen)
    trab = sum(float(r["total_trabajado"] or 0) for r in resumen)
    pagar_rows = sum(float(r["costo_total"] or 0) for r in rows)
    trab_rows = sum(float(r["total_trabajado"] or 0) for r in rows)
    assert pagar == EXPECTED_PAGAR
    assert trab == EXPECTED_TRABAJADO
    assert pagar_rows == EXPECTED_PAGAR
    assert trab_rows == EXPECTED_TRABAJADO


def test_detalle_empresa_isolation(conn):
    with conn.cursor() as cur:
        where_a, params_a = tc._build_detalle_filters(
            FECHA_INICIO,
            FECHA_TERMINO,
            contratista=CONTRATISTA,
            empresa="TALAGANTE",
        )
        where_b, params_b = tc._build_detalle_filters(
            FECHA_INICIO,
            FECHA_TERMINO,
            contratista=CONTRATISTA,
            empresa="ISLA DE MAIPO",
        )
        a = tc._query_detalle_resumen(cur, where_a, params_a)
        b = tc._query_detalle_resumen(cur, where_b, params_b)
    trab_a = sum(float(r["total_trabajado"] or 0) for r in a)
    trab_b = sum(float(r["total_trabajado"] or 0) for r in b)
    assert trab_a == EXPECTED_TRABAJADO
    assert trab_b != trab_a
    assert trab_b >= 0
