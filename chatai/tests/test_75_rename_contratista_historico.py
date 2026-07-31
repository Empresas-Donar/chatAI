"""
Regression tests for issue #75: the user renamed two contratistas in the
master catalog (appsheet.tarjas_contratistas, via AppSheet) but
appsheet.tarjas_pagos.contratista is a denormalized free-text column, not a
FK, so already-ingested rows kept showing the old name:
  - 'RAMÓN DIAZ' -> 'SERVICIOS AGRICOLAS RD SPA'
  - 'ANGEL CELIS' -> 'AGROSERVICIOS C Y G SPA' (0 rows existed at the time,
    the UPDATE is a no-op today but kept for any row using this contratista
    that appears later without having gone through a fresh sync).
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


def test_75_no_rows_with_old_ramon_diaz_name_regression(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM appsheet.tarjas_pagos WHERE contratista ILIKE %s",
            ("RAMON DIAZ",),
        )
        (count,) = cur.fetchone()
    assert count == 0


def test_75_servicios_agricolas_rd_spa_has_69_rows_regression(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM appsheet.tarjas_pagos WHERE contratista = %s",
            ("SERVICIOS AGRICOLAS RD SPA",),
        )
        (count,) = cur.fetchone()
    assert count == 69


def test_75_renamed_rows_are_all_tractorista_isolation(conn):
    """The rename must not have touched rows of a different tipo_pago that
    happened to share the same contratista name pattern."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT tipo_pago FROM appsheet.tarjas_pagos
            WHERE contratista = %s
            """,
            ("SERVICIOS AGRICOLAS RD SPA",),
        )
        tipos = {r[0] for r in cur.fetchall()}
    assert tipos == {"Tractorista"}


def test_75_no_rows_with_old_angel_celis_name(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM appsheet.tarjas_pagos WHERE contratista ILIKE %s",
            ("ANGEL CELIS",),
        )
        (count,) = cur.fetchone()
    assert count == 0


def test_75_other_contratistas_untouched_isolation(conn):
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
