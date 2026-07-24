"""
Regression tests for issue #38: columnas horas_extras, rendimiento, horas_trabajadas
deben ser NUMERIC en appsheet.tarjas_pagos (no TEXT).
"""
import decimal
import pytest
import psycopg2
import os
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


NUMERIC_COLUMNS = ("horas_extras", "rendimiento", "horas_trabajadas")


def test_38_horas_extras_is_numeric(conn):
    """Regression: horas_extras debe ser NUMERIC, no TEXT (issue #38)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'appsheet'
              AND table_name = 'tarjas_pagos'
              AND column_name = 'horas_extras'
            """
        )
        row = cur.fetchone()
    assert row is not None, "Column horas_extras not found in tarjas_pagos"
    assert row[0] == "numeric", (
        f"horas_extras should be NUMERIC but is {row[0]!r} — run 07_fix_numeric_types.sql"
    )


def test_38_rendimiento_is_numeric(conn):
    """Regression: rendimiento debe ser NUMERIC, no TEXT (issue #38)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'appsheet'
              AND table_name = 'tarjas_pagos'
              AND column_name = 'rendimiento'
            """
        )
        row = cur.fetchone()
    assert row is not None, "Column rendimiento not found in tarjas_pagos"
    assert row[0] == "numeric", (
        f"rendimiento should be NUMERIC but is {row[0]!r} — run 07_fix_numeric_types.sql"
    )


def test_38_horas_trabajadas_is_numeric(conn):
    """Regression: horas_trabajadas debe ser NUMERIC, no TEXT (issue #38)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'appsheet'
              AND table_name = 'tarjas_pagos'
              AND column_name = 'horas_trabajadas'
            """
        )
        row = cur.fetchone()
    assert row is not None, "Column horas_trabajadas not found in tarjas_pagos"
    assert row[0] == "numeric", (
        f"horas_trabajadas should be NUMERIC but is {row[0]!r} — run 07_fix_numeric_types.sql"
    )


def test_38_fix_numeric_types_tarjas_regression(conn):
    """
    Regression test: SUM(horas_trabajadas) must return a numeric result directly,
    without requiring defensive regex casting.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT SUM(horas_trabajadas), AVG(horas_trabajadas), SUM(horas_extras)
            FROM appsheet.tarjas_pagos
            WHERE horas_trabajadas IS NOT NULL
            """
        )
        row = cur.fetchone()
    assert row is not None
    # psycopg2 returns Decimal for NUMERIC columns — verify it's a numeric type
    sum_horas, avg_horas, sum_extras = row
    assert sum_horas is None or isinstance(sum_horas, (int, float, decimal.Decimal)), (
        f"SUM(horas_trabajadas) returned unexpected type: {type(sum_horas)}"
    )
    # The column must have actual non-zero values
    assert sum_horas is not None and sum_horas > 0, (
        f"SUM(horas_trabajadas) returned {sum_horas!r} — expected positive total"
    )


def test_38_horas_trabajadas_decimal_values_preserved(conn):
    """
    Horas_trabajadas contains decimal values (e.g. 6.5, 4.5) — verify they
    are stored and retrieved correctly as NUMERIC, not truncated.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT horas_trabajadas
            FROM appsheet.tarjas_pagos
            WHERE horas_trabajadas IS NOT NULL
              AND horas_trabajadas > 0
            LIMIT 100
            """
        )
        rows = cur.fetchall()
    # There should be some rows with values
    assert len(rows) > 0, "No non-zero horas_trabajadas rows found — check data"
    values = [r[0] for r in rows]
    # At least one value should be non-integer (decimal)
    has_decimal = any(v % 1 != 0 for v in values if v is not None)
    assert has_decimal, (
        "Expected at least one decimal value in horas_trabajadas (e.g. 6.5) "
        "but all values appear to be integers. Column may have been altered to INTEGER."
    )


def test_38_all_numeric_columns_present(conn):
    """All three columns exist in tarjas_pagos with NUMERIC type."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'appsheet'
              AND table_name = 'tarjas_pagos'
              AND column_name IN ('horas_extras', 'rendimiento', 'horas_trabajadas')
            ORDER BY column_name
            """
        )
        rows = {r[0]: r[1] for r in cur.fetchall()}
    assert len(rows) == 3, f"Expected 3 columns, found: {list(rows.keys())}"
    for col in NUMERIC_COLUMNS:
        assert rows[col] == "numeric", (
            f"Column {col!r} should be 'numeric' but is {rows[col]!r}"
        )


def test_38_tarjas_reporte_view_horas_trabajadas_no_nulls_on_valid_rows(conn):
    """
    tarjas_reporte view must return non-null horas_trabajadas for rows with
    horas_trabajadas > 0 in the source table (no longer zeroed out by regex guard).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM appsheet.tarjas_reporte
            WHERE horas_trabajadas > 0
            """
        )
        row = cur.fetchone()
    count = row[0]
    assert count > 0, (
        "tarjas_reporte returned 0 rows with horas_trabajadas > 0 — "
        "view may still use broken TEXT casting"
    )


def test_38_cross_table_isolation(conn):
    """
    Isolation check: tarjas_pagos and tarjas_det_supervisor are distinct tables.
    tarjas_det_supervisor should not have numeric hour columns (only 4 text ID columns).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'appsheet'
              AND table_name = 'tarjas_det_supervisor'
            """
        )
        det_cols = {r[0] for r in cur.fetchall()}
    # tarjas_det_supervisor must NOT have horas_trabajadas — different table
    assert "horas_trabajadas" not in det_cols, (
        "horas_trabajadas found in tarjas_det_supervisor — schema mismatch, check migration"
    )
    # tarjas_det_supervisor should only have its 4 ID columns
    assert det_cols == {"id_detalle", "id_supervisor", "id_trabajador", "actualizacion"}, (
        f"tarjas_det_supervisor has unexpected columns: {det_cols}"
    )
