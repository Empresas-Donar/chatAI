"""
Detalle operacional hid August 2026 monthly bonuses for MULTISERVICIOS
BONHOMIA SPA / ZUÑIGA: rows are tipo_pago='Bono', estado='Pendiente', and
nombre_campo was NULL (AppSheet omitted the campo; CC 878/800 → ZUÑIGA).

Detalle now includes tipo_pago='Bono' even while Pendiente. nombre_campo is
resolved from the cost center so the Empresa filter still matches.

Reported URL:
  /tarjas/detalle?fil-from=2026-08-26&fil-to=2026-09-01
    &fil-contratista=MULTISERVICIOS BONHOMIA SPA&fil-empresa=ZUÑIGA

Run:
    python -m pytest chatai/tests/test_158_detalle_bonos_pendiente.py -v
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

CONTRATISTA = "MULTISERVICIOS BONHOMIA SPA"
EMPRESA = "ZUÑIGA"
FECHA_INICIO = "2026-08-26"
FECHA_TERMINO = "2026-09-01"
BONO_WORKERS = {
    "Carmen Benavides",
    "Cristian González Dinamarca",
    "Mariana Vega Pavéz",
    "Yasmileth Pacheco",
}
EXPECTED_BONO_TOTAL = 250_413


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


def test_detalle_filters_include_pending_bono():
    src = _fn_source("_build_detalle_filters")
    assert "(estado = 'Aprobado' OR LOWER(TRIM(tipo_pago)) = 'bono')" in src
    assert 'estado = \'Aprobado\'"' not in src.replace(
        "(estado = 'Aprobado' OR LOWER(TRIM(tipo_pago)) = 'bono')", ""
    )


def test_august_bonos_exist_pendiente_for_bonhomia(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trabajador, estado, nombre_campo, total_pagar
            FROM appsheet.tarjas_pagos
            WHERE fecha::date BETWEEN %s AND %s
              AND contratista = %s
              AND LOWER(TRIM(tipo_pago)) = 'bono'
            ORDER BY trabajador
            """,
            (FECHA_INICIO, FECHA_TERMINO, CONTRATISTA),
        )
        rows = cur.fetchall()
    names = {r[0] for r in rows}
    assert names == BONO_WORKERS
    assert all(r[1] == "Pendiente" for r in rows)
    assert all(r[2] == EMPRESA for r in rows)
    assert sum(float(r[3]) for r in rows) == EXPECTED_BONO_TOTAL


def test_detalle_bonhomia_zuniga_includes_bonos(conn):
    with conn.cursor() as cur:
        where, params = tc._build_detalle_filters(
            FECHA_INICIO,
            FECHA_TERMINO,
            contratista=CONTRATISTA,
            empresa=EMPRESA,
        )
        resumen = tc._query_detalle_resumen(cur, where, params)
        rows = tc._query_detalle_rows(cur, where, params)

    bono_resumen = [
        r for r in resumen if (r["tipo_pago"] or "").strip().lower() == "bono"
    ]
    assert bono_resumen, "resumen must include a Bono slice"
    assert sum(float(r["total_pagar"] or 0) for r in bono_resumen) == EXPECTED_BONO_TOTAL

    bono_rows = [r for r in rows if (r["tipo_pago"] or "").strip().lower() == "bono"]
    assert bono_rows
    assert all((r["labor"] or "") == "Bono mensual" for r in bono_rows)
    assert sum(float(r["costo_total"] or 0) for r in bono_rows) == EXPECTED_BONO_TOTAL
