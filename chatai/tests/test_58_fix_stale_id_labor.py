"""
Regression tests for issue #58: tarjas_pagos.id_labor can go stale when
tarjas_labores.codigo_labor is corrected after a row's id_labor was already
set — trg_set_id_labor (issue #27) only recalculates on INSERT or
UPDATE OF labor, and the original backfill (04_backfill_id_labor.sql) only
fills id_labor IS NULL, so a stale non-NULL value is never re-synced.

Case found: id_Resumen='87ae12dc' (SUPERVISOR HUERTO, HERBI ML SPA, Isla de
Maipo, 23 julio 2026) had id_labor='9.10' while tarjas_labores.codigo_labor
for that labor is '9.1' — the mismatch left the row without a product_id in
tarjas_reporte_odoo, showing as "Incompleta" in the Odoo export preview.
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


def test_58_no_stale_id_labor_mismatch_regression(conn):
    """No row in tarjas_pagos should have an id_labor that disagrees with
    the current codigo_labor for its exact labor text."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos p
            JOIN appsheet.tarjas_labores l ON trim(l.labor) = trim(p.labor)
            WHERE p.id_labor IS DISTINCT FROM l.codigo_labor
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, f"{count} filas con id_labor desactualizado respecto a tarjas_labores"


def test_58_specific_row_fixed(conn):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT id_labor FROM appsheet.tarjas_pagos WHERE "id_Resumen" = %s',
            ("87ae12dc",),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "9.1"


def test_58_odoo_export_no_longer_incomplete_for_this_range(conn):
    """The Odoo export view must no longer have a NULL product_id row for
    the exact filters where the bug was reported (HERBI ML SPA / Isla de
    Maipo, 22-28 julio 2026)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_reporte_odoo
            WHERE "Vendedor" = 'HERBI ML SPA' AND nombre_campo = 'ISLA DE MAIPO'
              AND fecha BETWEEN '2026-07-22' AND '2026-07-28'
              AND "order_line/product_id" IS NULL
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, f"{count} filas sin product_id para HERBI ML SPA / Isla de Maipo (22-28 jul)"


def test_58_cross_table_isolation_tarjas_labores_untouched(conn):
    """Isolation check: the fix only updates tarjas_pagos.id_labor — it
    must not have altered tarjas_labores.codigo_labor itself."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT codigo_labor FROM appsheet.tarjas_labores WHERE labor = %s",
            ("SUPERVISOR HUERTO",),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "9.1"
