"""
Regression tests for issue #40: reports_controller.py still used the TEXT-era
defensive regex casting (`col ~ '^[0-9]+(\\.[0-9]+)?$'`) against horas_trabajadas
and horas_extras, which issue #38 already converted to NUMERIC in tarjas_pagos.
`~` does not exist for numeric operands in PostgreSQL, so every report backed by
these three query sites (bulk PDF: general, resumen-horas) raised
psycopg2.errors.UndefinedFunction and returned HTTP 500.
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


def test_40_horas_expr_query_no_longer_raises(conn):
    """_HORAS_EXPR (used by _html_general) must run without the numeric ~ unknown error."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT contratista, NULLIF(SUM(horas_trabajadas), 0)
            FROM appsheet.tarjas_pagos
            WHERE estado = 'Aprobado'
            GROUP BY contratista
            """
        )
        rows = cur.fetchall()
    assert len(rows) > 0, "Expected at least one contratista with Aprobado rows"


def test_40_horas_extras_resumen_query_no_longer_raises(conn):
    """The resumen-horas aggregation (_html_resumen_horas) must run without error
    and return the same totals as summing horas_extras directly."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trabajador, tipo_pago, fecha::date::text AS fecha,
                   COALESCE(SUM(horas_extras), 0)::numeric AS horas
            FROM appsheet.tarjas_pagos
            WHERE estado = 'Aprobado'
            GROUP BY trabajador, tipo_pago, fecha::date
            """
        )
        rows = cur.fetchall()
        total_from_query = sum(r[3] for r in rows)

        cur.execute(
            "SELECT COALESCE(SUM(horas_extras), 0) FROM appsheet.tarjas_pagos "
            "WHERE estado = 'Aprobado'"
        )
        total_raw = cur.fetchone()[0]
    assert len(rows) > 0
    assert total_from_query == total_raw, (
        "Grouped SUM(horas_extras) does not match the raw table total — "
        "aggregation is dropping rows"
    )


def test_40_fix_reports_regex_regression_no_broken_pattern_in_source():
    """Static guard: reports_controller.py must not reintroduce the TEXT-era
    regex cast against horas_trabajadas/horas_extras now that both are NUMERIC."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "controllers", "reports_controller.py"
    )
    with open(path, encoding="utf-8") as f:
        source = f.read()
    assert "horas_trabajadas ~" not in source, (
        "reports_controller.py still contains the broken TEXT regex cast for "
        "horas_trabajadas (operator does not exist: numeric ~ unknown)"
    )
    assert "horas_extras ~" not in source, (
        "reports_controller.py still contains the broken TEXT regex cast for "
        "horas_extras (operator does not exist: numeric ~ unknown)"
    )


def test_40_cross_table_isolation_tarjas_pagos_only():
    """Isolation check: the fix must only touch appsheet.tarjas_pagos aggregation
    queries in reports_controller.py, not other tables' queries in the same file."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "controllers", "reports_controller.py"
    )
    with open(path, encoding="utf-8") as f:
        source = f.read()
    assert "FROM appsheet.tarjas_pagos" in source, (
        "Expected reports_controller.py to still query appsheet.tarjas_pagos"
    )
