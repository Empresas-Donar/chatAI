"""
Regression tests for issue #152: /tarjas/detalle-tractorista was empty for
August 2026 because it queried appsheet.tarjas_reporte (estado = Aprobado,
amount = total_pagar). August tractorista rows are Pendiente and the money
is in total_tractor. Screen, Excel and PDF now read tarjas_pagos.

Run:
    python -m pytest chatai/tests/test_152_detalle_tractorista_pendiente.py -v
"""

import ast
import asyncio
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

FECHA_INICIO = "2026-08-01"
FECHA_TERMINO = "2026-09-06"


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


def run(coro):
    return asyncio.run(coro)


def _fn_source(name: str) -> str:
    src = TARJAS_CTRL.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"function {name} not found")


def test_152_api_queries_pagos_not_reporte_regression():
    src = _fn_source("get_tarjas_detalle_tractorista")
    assert "tarjas_pagos" in src
    assert "total_tractor" in src
    assert "tarjas_reporte" not in src
    assert "total_labor" not in src


def test_152_filters_query_pagos_regression():
    src = _fn_source("get_tarjas_detalle_tractorista_filters")
    assert "tarjas_pagos" in src
    assert "tarjas_reporte" not in src


def test_152_pdf_builder_queries_pagos_regression():
    src = _fn_source("_build_detalle_tractorista_html")
    assert "_fetch_detalle_tractorista_rows" in src
    assert "tarjas_reporte" not in src


def test_152_excel_queries_pagos_regression():
    src = _fn_source("download_tarjas_detalle_tractorista_excel")
    assert "_fetch_detalle_tractorista_rows" in src
    assert "tarjas_reporte" not in src


def test_152_august_range_returns_pending_rows(conn):
    """The reported URL range must not be empty — August is all Pendiente."""
    data = run(
        tc.get_tarjas_detalle_tractorista(
            fecha_inicio=FECHA_INICIO,
            fecha_termino=FECHA_TERMINO,
            contratista=None,
            empresa=None,
            centro_costo=None,
            labor=None,
            campo=None,
        )
    )
    assert data["count"] > 0, (
        "detalle-tractorista returned 0 rows for 2026-08-01..2026-09-06 "
        "(Pendiente rows were being dropped via tarjas_reporte)"
    )
    assert data["jornadas"] > 0
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(total_tractor), 0), COUNT(*)
            FROM appsheet.tarjas_pagos
            WHERE LOWER(TRIM(tipo_pago)) = 'tractorista'
              AND fecha::date BETWEEN %s AND %s
            """,
            (FECHA_INICIO, FECHA_TERMINO),
        )
        expected_sum, expected_n = cur.fetchone()
    assert float(data["total"]) == float(expected_sum)
    assert int(data["jornadas"]) == int(expected_n)


def test_152_pdf_html_includes_august_contractors(conn):
    with conn.cursor() as cur:
        html = tc._build_detalle_tractorista_html(
            cur,
            FECHA_INICIO,
            FECHA_TERMINO,
        )
    assert "SERVICIOS AGRICOLAS RD SPA" in html or "AGROSERVICIOS" in html
    assert "Jornada Tractor" in html or "jornada tractor" in html.lower()


def test_152_detalle_operacional_exposes_trabajado_isolation():
    """Cuadrilla detalle keeps total_pagar and adds total_trabajado
    from tarjas_pagos — not tractorista money."""
    src = _fn_source("_query_detalle_rows")
    assert "tarjas_pagos" in src
    assert "total_trabajado" in src
    assert "total_pagar" in src
    assert "total_tractor" not in src
