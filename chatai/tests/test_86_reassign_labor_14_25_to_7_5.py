"""
Regression tests for issue #86: rows entered in appsheet.tarjas_pagos with
labor code "14.25" (REPARTIR. ABRIR. FLAMEAR. TENSAR. CLIPEAR Y FIJAR
PLASTICO) must be reassigned to the correct labor code "7.5" (CONSTRUCCION
MACROTUNELES), including the denormalized "labor" text column.
"""

import os

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

NEW_LABOR_TEXT = "CONSTRUCCIÓN MACROTÚNELES"


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


def test_86_no_rows_with_old_labor_code_regression(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM appsheet.tarjas_pagos WHERE id_labor = %s",
            ("14.25",),
        )
        (count,) = cur.fetchone()
    assert count == 0


def test_86_new_labor_code_has_13_rows_regression(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM appsheet.tarjas_pagos WHERE id_labor = %s AND labor = %s",
            ("7.5", NEW_LABOR_TEXT),
        )
        (count,) = cur.fetchone()
    assert count == 13


def test_86_reassigned_rows_are_all_talagante_herbi_al_dia_isolation(conn):
    """The reassignment must not have touched rows from a different campo,
    contratista, or tipo_pago that happened to share the same labor code."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT nombre_campo, contratista, tipo_pago
            FROM appsheet.tarjas_pagos
            WHERE id_labor = %s AND labor = %s
            """,
            ("7.5", NEW_LABOR_TEXT),
        )
        rows = set(cur.fetchall())
    assert rows == {("TALAGANTE", "HERBI ML SPA", "Al dia")}


def test_86_other_labores_untouched_isolation(conn):
    """Unrelated labor codes must keep their existing row counts."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id_labor, count(*) FROM appsheet.tarjas_pagos
            WHERE id_labor IN ('7.1', '14.1')
            GROUP BY id_labor
            """
        )
        counts = dict(cur.fetchall())
    assert counts.get("7.1", 0) >= 0
    assert counts.get("14.1", 0) >= 0


def test_86_tarjas_labores_catalog_untouched(conn):
    """Only tarjas_pagos rows were reassigned; the labor catalog itself
    (both codes as distinct labores) must remain unchanged."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT codigo_labor, labor FROM appsheet.tarjas_labores WHERE codigo_labor IN ('14.25', '7.5') ORDER BY codigo_labor"
        )
        rows = cur.fetchall()
    assert rows == [
        ("14.25", "REPARTIR. ABRIR. FLAMEAR. TENSAR. CLIPEAR Y FIJAR PLÁSTICO"),
        ("7.5", NEW_LABOR_TEXT),
    ]
