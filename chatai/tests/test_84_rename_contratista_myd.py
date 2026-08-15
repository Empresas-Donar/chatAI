"""
Regression tests for issue #84: an Excel upload from the intranet for
contratista "MYD SPA" (campo Zúñiga) was not recognized by Odoo because
appsheet.tarjas_pagos.contratista is a denormalized free-text column used
directly as partner_id/Vendedor in tarjas_reporte_odoo, and it didn't match
the real Odoo partner name "PRESTACION DE SERVICIOS M Y D SPA".
"""

import os

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

NEW_NAME = "PRESTACION DE SERVICIOS M Y D SPA"


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


def test_84_no_rows_with_old_myd_name_regression(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM appsheet.tarjas_pagos WHERE contratista ILIKE %s",
            ("MYD SPA",),
        )
        (count,) = cur.fetchone()
    assert count == 0


def test_84_new_name_has_26_rows_regression(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM appsheet.tarjas_pagos WHERE contratista = %s",
            (NEW_NAME,),
        )
        (count,) = cur.fetchone()
    assert count == 26


def test_84_renamed_rows_are_all_zuniga_trato_isolation(conn):
    """The rename must not have touched rows from a different campo or
    tipo_pago that happened to share the same contratista name."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT nombre_campo, tipo_pago FROM appsheet.tarjas_pagos
            WHERE contratista = %s
            """,
            (NEW_NAME,),
        )
        rows = set(cur.fetchall())
    assert rows == {("ZUÑIGA", "trato")}


def test_84_tarjas_contratistas_catalog_updated(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT nombre FROM appsheet.tarjas_contratistas WHERE id_contratista = %s",
            ("54SA6ASS4",),
        )
        row = cur.fetchone()
    assert row == (NEW_NAME,)


def test_84_other_contratistas_untouched_isolation(conn):
    """Unrelated contratistas must keep their existing row counts."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT contratista, count(*) FROM appsheet.tarjas_pagos
            WHERE contratista IN ('HERBI ML SPA', 'MULTISERVICIOS BONHOMIA SPA')
            GROUP BY contratista
            """
        )
        counts = dict(cur.fetchall())
    assert counts.get("HERBI ML SPA", 0) > 0
    assert counts.get("MULTISERVICIOS BONHOMIA SPA", 0) > 0
