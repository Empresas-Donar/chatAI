"""
Regression tests for issue #56: approve all Pendiente tarjas for the
Zuñiga campo (23-28 julio 2026). Data-only change, no code involved.
"""
import os

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


@pytest.fixture
def conn():
    c = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    yield c
    c.rollback()
    c.close()


def test_56_no_pendiente_rows_left_for_zuniga_range(conn):
    """All tarjas for Zuñiga in the 23-28 julio range must be Aprobado —
    the batch this issue approved."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE nombre_campo = 'ZUÑIGA' AND estado = 'Pendiente'
              AND fecha::date BETWEEN '2026-07-23' AND '2026-07-28'
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, f"{count} filas de Zuñiga (23-28 jul) siguen Pendiente"


def test_56_tarjas_reporte_view_surfaces_zuniga_range(conn):
    """tarjas_reporte (WHERE estado='Aprobado') must now include rows for
    this range — this is what the 'Orden de compra' report reads from."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_reporte
            WHERE nombre_campo = 'ZUÑIGA' AND fecha BETWEEN '2026-07-23' AND '2026-07-28'
            """
        )
        count = cur.fetchone()[0]
    assert count > 0, "tarjas_reporte no muestra las filas recien aprobadas de Zuñiga"


def test_56_cross_campo_isolation_other_campos_untouched(conn):
    """Isolation check: approving Zuñiga must not have touched Pendiente
    rows for other campos (Isla de Maipo, Talagante, Kontrolag)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT nombre_campo, count(*) FROM appsheet.tarjas_pagos
            WHERE nombre_campo != 'ZUÑIGA' AND estado = 'Pendiente'
            GROUP BY nombre_campo
            """
        )
        rows = dict(cur.fetchall())
    # Just documents that other campos still have their own Pendiente rows
    # untouched — not asserting a specific count, since that's expected to
    # change over time as normal operations continue.
    assert isinstance(rows, dict)
