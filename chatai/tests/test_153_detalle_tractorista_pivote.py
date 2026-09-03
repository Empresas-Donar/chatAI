"""
Regression tests for issue #153: /tarjas/detalle-tractorista must render
Looker's nested pivot (contratista → trabajador → labor, rows = fechas with
tarjas, cells = SUM(total_tractor)), not the previous flat tables.

Screen JSON, Excel and PDF share _fetch_detalle_tractorista_rows +
_build_detalle_tractorista_pivots (issues #52/#116/#152).

Run:
    python -m pytest chatai/tests/test_153_detalle_tractorista_pivote.py -v
"""

import ast
import asyncio
import os
import re
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
DETALLE_JS = (
    Path(__file__).parent.parent
    / "frontend"
    / "static"
    / "tarjas_detalle_tractorista.js"
)

AUG_INICIO = "2026-08-01"
AUG_TERMINO = "2026-09-06"
JUL_INICIO = "2026-07-01"
JUL_TERMINO = "2026-07-31"


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
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"function {name} not found")


class TestBuildPivotHelper:
    def test_153_matrix_totals_and_empty_cells(self):
        rows = [
            {
                "fecha": "2026-07-01",
                "contratista": "AGROSERVICIOS C Y G SPA",
                "trabajador": "Cristian Gonzalez Pino",
                "labor": "Hora Extra",
                "monto": 3400,
            },
            {
                "fecha": "2026-07-01",
                "contratista": "AGROSERVICIOS C Y G SPA",
                "trabajador": "Cristian Gonzalez Pino",
                "labor": "Jornada Tractor normal",
                "monto": 59400,
            },
            {
                "fecha": "2026-07-03",
                "contratista": "AGROSERVICIOS C Y G SPA",
                "trabajador": "Cristian Gonzalez Pino",
                "labor": "Jornada Tractor normal",
                "monto": 59400,
            },
        ]
        pivots = tc._build_detalle_tractorista_pivots(rows)
        assert len(pivots) == 1
        p = pivots[0]
        assert p["contratista"] == "AGROSERVICIOS C Y G SPA"
        assert p["dates"] == ["2026-07-01", "2026-07-03"]
        assert "2026-07-02" not in p["dates"]
        he = tc._detalle_tract_col_key("Cristian Gonzalez Pino", "Hora Extra")
        jt = tc._detalle_tract_col_key(
            "Cristian Gonzalez Pino", "Jornada Tractor normal"
        )
        assert p["matrix"]["2026-07-01"][he] == 3400
        assert p["matrix"]["2026-07-01"][jt] == 59400
        assert p["matrix"]["2026-07-03"][he] is None
        assert p["matrix"]["2026-07-03"][jt] == 59400
        assert p["date_totals"]["2026-07-01"] == 62800
        assert p["col_totals"][he] == 3400
        assert p["grand_total"] == 122200

    def test_153_one_block_per_contratista(self):
        rows = [
            {
                "fecha": "2026-07-01",
                "contratista": "B Co",
                "trabajador": "Ana",
                "labor": "L1",
                "monto": 10,
            },
            {
                "fecha": "2026-07-01",
                "contratista": "A Co",
                "trabajador": "Bob",
                "labor": "L1",
                "monto": 20,
            },
        ]
        pivots = tc._build_detalle_tractorista_pivots(rows)
        assert [p["contratista"] for p in pivots] == ["A Co", "B Co"]
        assert pivots[0]["grand_total"] == 20
        assert pivots[1]["grand_total"] == 10

    def test_153_empty_rows_produce_no_pivots(self):
        assert tc._build_detalle_tractorista_pivots([]) == []


class TestApiPivotMatchesPagos:
    def test_153_cells_equal_sum_total_tractor(self, conn):
        data = run(
            tc.get_tarjas_detalle_tractorista(
                fecha_inicio=JUL_INICIO,
                fecha_termino=JUL_TERMINO,
                contratista=None,
                empresa=None,
                centro_costo=None,
                labor=None,
                campo=None,
            )
        )
        assert data["pivots"], "July 2026 tractorista pivot should not be empty"
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    fecha::date::text AS fecha,
                    COALESCE(contratista, '(sin contratista)') AS contratista,
                    COALESCE(trabajador, '(sin nombre)') AS trabajador,
                    COALESCE(labor, '') AS labor,
                    COALESCE(SUM(total_tractor), 0) AS monto
                FROM appsheet.tarjas_pagos
                WHERE LOWER(TRIM(tipo_pago)) = 'tractorista'
                  AND fecha::date BETWEEN %s AND %s
                GROUP BY 1, 2, 3, 4
                """,
                (JUL_INICIO, JUL_TERMINO),
            )
            expected = {(r[0], r[1], r[2], r[3]): float(r[4]) for r in cur.fetchall()}
        for p in data["pivots"]:
            for fecha in p["dates"]:
                for col in p["columns"]:
                    cell = p["matrix"][fecha][col["key"]]
                    key = (
                        fecha,
                        p["contratista"],
                        col["trabajador"],
                        col["labor"],
                    )
                    exp = expected.get(key, 0.0)
                    if cell is None:
                        assert exp == 0.0
                    else:
                        assert abs(float(cell) - exp) < 0.01

    def test_153_column_and_grand_totals_match_matrix(self):
        data = run(
            tc.get_tarjas_detalle_tractorista(
                fecha_inicio=JUL_INICIO,
                fecha_termino=JUL_TERMINO,
                contratista=None,
                empresa=None,
                centro_costo=None,
                labor=None,
                campo=None,
            )
        )
        overall = 0.0
        for p in data["pivots"]:
            for col in p["columns"]:
                recomputed = sum(p["matrix"][d][col["key"]] or 0.0 for d in p["dates"])
                assert abs(recomputed - p["col_totals"][col["key"]]) < 0.01
            for d in p["dates"]:
                row_sum = sum(v or 0.0 for v in p["matrix"][d].values())
                assert abs(row_sum - p["date_totals"][d]) < 0.01
            assert abs(sum(p["col_totals"].values()) - p["grand_total"]) < 0.01
            overall += p["grand_total"]
        assert abs(overall - float(data["total"])) < 0.01

    def test_153_august_range_not_empty_pending(self):
        data = run(
            tc.get_tarjas_detalle_tractorista(
                fecha_inicio=AUG_INICIO,
                fecha_termino=AUG_TERMINO,
                contratista=None,
                empresa=None,
                centro_costo=None,
                labor=None,
                campo=None,
            )
        )
        assert data["count"] > 0
        assert data["pivots"]
        assert data["total"] > 0
        opts = data.get("filter_options") or {}
        assert opts.get("contratistas")
        assert opts.get("labores")

    def test_153_no_invented_calendar_days(self, conn):
        data = run(
            tc.get_tarjas_detalle_tractorista(
                fecha_inicio=JUL_INICIO,
                fecha_termino=JUL_TERMINO,
                contratista=None,
                empresa=None,
                centro_costo=None,
                labor=None,
                campo=None,
            )
        )
        with conn.cursor() as cur:
            for p in data["pivots"]:
                cur.execute(
                    """
                    SELECT DISTINCT fecha::date::text
                    FROM appsheet.tarjas_pagos
                    WHERE LOWER(TRIM(tipo_pago)) = 'tractorista'
                      AND COALESCE(contratista, '(sin contratista)') = %s
                      AND fecha::date BETWEEN %s AND %s
                    ORDER BY 1
                    """,
                    (p["contratista"], JUL_INICIO, JUL_TERMINO),
                )
                expected = [r[0] for r in cur.fetchall()]
                assert p["dates"] == expected


class TestSharedBuilderAndFormats:
    def test_153_excel_and_pdf_use_same_pivot_helper(self):
        excel_src = _fn_source("download_tarjas_detalle_tractorista_excel")
        html_src = _fn_source("_build_detalle_tractorista_html")
        api_src = _fn_source("get_tarjas_detalle_tractorista")
        for src, name in (
            (excel_src, "excel"),
            (html_src, "pdf html"),
            (api_src, "json api"),
        ):
            assert "_build_detalle_tractorista_pivots" in src, name
            assert "_fetch_detalle_tractorista_rows" in src, name

    def test_153_pdf_html_uses_ddmmyyyy_and_suma_total(self, conn):
        with conn.cursor() as cur:
            html = tc._build_detalle_tractorista_html(cur, JUL_INICIO, JUL_TERMINO)
        assert "Suma total" in html
        assert re.search(r"\b\d{2}/\d{2}/2026\b", html)
        assert not re.search(r">2026-07-\d{2}<", html)
        assert "Jornada Tractor" in html or "jornada tractor" in html.lower()

    def test_153_js_formats_dates_ddmmyyyy(self):
        src = DETALLE_JS.read_text(encoding="utf-8")
        assert "formatDate" in src
        assert "${d}/${m}/${y}" in src
        assert "Intl.NumberFormat('es-CL'" in src
        assert "applyFilterOptions" in src
        assert "filter_options" in src
        assert "new Option" in src

    def test_153_filters_merge_empresa_campo(self):
        html = (
            Path(__file__).parent.parent
            / "frontend"
            / "templates"
            / "tarjas_detalle_tractorista.html"
        ).read_text(encoding="utf-8")
        assert 'id="fil-empresa"' in html
        assert "Empresa / Campo" in html
        assert 'id="fil-campo"' not in html
        src = DETALLE_JS.read_text(encoding="utf-8")
        assert "fil-campo" in src
        assert "fillSelect('fil-campo'" not in src

    def test_153_detalle_operacional_exposes_trabajado_isolation(self):
        src = _fn_source("_query_detalle_rows")
        assert "tarjas_pagos" in src
        assert "total_trabajado" in src
        assert "total_pagar" in src
        api_src = _fn_source("get_tarjas_detalle_tractorista")
        assert "tarjas_reporte" not in api_src
        assert "total_labor" not in api_src
