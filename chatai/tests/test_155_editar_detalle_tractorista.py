"""Inline edit of estado (row) and total_tractor (cell) on detalle tractorista."""

import os
import sys

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc  # noqa: E402
import psycopg2  # noqa: E402


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


def test_155_parse_clp_int():
    assert tc._parse_clp_int("$34.500") == 34500
    assert tc._parse_clp_int("34500") == 34500
    assert tc._parse_clp_int(34500) == 34500
    with pytest.raises(HTTPException):
        tc._parse_clp_int(-1)
    with pytest.raises(HTTPException):
        tc._parse_clp_int("")


def test_155_pivot_includes_date_estados():
    rows = [
        {
            "fecha": "2026-08-03",
            "contratista": "AGROSERVICIOS C Y G SPA",
            "trabajador": "Cristian Gonzalez",
            "labor": "Jornada Tractor normal",
            "monto": 34500,
            "estado": "Pendiente",
            "n_estados": 1,
        },
        {
            "fecha": "2026-08-04",
            "contratista": "AGROSERVICIOS C Y G SPA",
            "trabajador": "Cristian Gonzalez",
            "labor": "Jornada Tractor normal",
            "monto": 23000,
            "estado": "Aprobado",
            "n_estados": 1,
        },
    ]
    p = tc._build_detalle_tractorista_pivots(rows)[0]
    assert p["date_estados"]["2026-08-03"] == "Pendiente"
    assert p["date_estados"]["2026-08-04"] == "Aprobado"


def test_155_js_wires_patch_endpoints():
    src = (
        __import__("pathlib")
        .Path(__file__)
        .parent.parent
        / "frontend"
        / "static"
        / "tarjas_detalle_tractorista.js"
    ).read_text(encoding="utf-8")
    assert "/api/tarjas/detalle-tractorista/fila" in src
    assert "/api/tarjas/detalle-tractorista/celda" in src
    assert "tdt-estado" in src
    assert "tdt-monto" in src


def test_155_update_estado_and_monto_then_rollback(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT contratista, fecha::date::text AS fecha, trabajador, labor,
                   COALESCE(total_tractor, 0), estado, "id_Resumen"
            FROM appsheet.tarjas_pagos
            WHERE LOWER(TRIM(tipo_pago)) = 'tractorista'
              AND contratista IS NOT NULL
              AND trabajador IS NOT NULL
              AND labor IS NOT NULL
            ORDER BY fecha::date DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row is None:
            pytest.skip("no tractorista rows")
        contratista, fecha, trabajador, labor, monto, estado, _id = row
        other = "Aprobado" if estado != "Aprobado" else "Pendiente"
        n = tc._update_detalle_tractorista_estado(cur, contratista, fecha, other)
        assert n >= 1
        cur.execute(
            """
            SELECT DISTINCT estado FROM appsheet.tarjas_pagos
            WHERE LOWER(TRIM(tipo_pago)) = 'tractorista'
              AND contratista = %s AND fecha::date = %s
            """,
            (contratista, fecha),
        )
        assert {r[0] for r in cur.fetchall()} == {other}

        new_monto = int(monto) + 1
        n_cell = tc._update_detalle_tractorista_monto(
            cur, contratista, fecha, trabajador, labor, new_monto
        )
        assert n_cell >= 1
        cur.execute(
            """
            SELECT COALESCE(SUM(total_tractor), 0)
            FROM appsheet.tarjas_pagos
            WHERE LOWER(TRIM(tipo_pago)) = 'tractorista'
              AND contratista = %s AND fecha::date = %s
              AND trabajador = %s AND COALESCE(labor, '') = %s
            """,
            (contratista, fecha, trabajador, labor),
        )
        assert int(cur.fetchone()[0]) == new_monto
    conn.rollback()
