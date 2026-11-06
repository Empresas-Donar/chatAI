"""Tarjas cost-center catalog: validation and a rolled-back write."""

import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv
from fastapi import HTTPException
from psycopg2 import errors

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from controllers.centros_costo_controller import (  # noqa: E402
    clean_code,
    clean_distribucion,
    clean_name,
    distribution_lines,
    require_campo,
    usage_count,
)


def _connect():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=20,
    )


@pytest.fixture
def cur():
    conn = _connect()
    conn.autocommit = False
    cursor = conn.cursor()
    try:
        yield cursor
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def test_code_accepts_appsheet_codes():
    assert clean_code(" 800 ") == "800"
    assert clean_code("616-c2") == "616-c2"


def test_code_rejects_blank_and_spaces():
    with pytest.raises(HTTPException) as blank:
        clean_code("  ")
    assert blank.value.status_code == 422
    with pytest.raises(HTTPException):
        clean_code("800 1")


def test_name_collapses_space_and_rejects_empty():
    assert clean_name("  CAMPO   ZÚÑIGA ") == "CAMPO ZÚÑIGA"
    with pytest.raises(HTTPException) as empty:
        clean_name("   ")
    assert empty.value.status_code == 422


def test_distribution_accepts_lines_that_sum_to_100():
    assert clean_distribucion([]) is None
    stored = clean_distribucion([("410", "60"), ("411", "40,00")])
    assert stored == '{"410": 60.00, "411": 40.00}'


def test_distribution_rejects_a_total_other_than_100():
    with pytest.raises(HTTPException) as bad:
        clean_distribucion([("410", "60"), ("411", "30")])
    assert bad.value.status_code == 422
    assert "100" in bad.value.detail


def test_distribution_rejects_duplicate_and_blank_accounts():
    with pytest.raises(HTTPException):
        clean_distribucion([("410", "60"), ("410", "40")])
    with pytest.raises(HTTPException):
        clean_distribucion([("", "100")])
    with pytest.raises(HTTPException):
        clean_distribucion([("410", "10.125"), ("411", "89.875")])


def test_distribution_lines_round_to_cents():
    lines = distribution_lines({"410": 7.0600000000000005, "411": 92.94})
    assert lines == [
        {"odoo_id": "410", "porcentaje": "7.06"},
        {"odoo_id": "411", "porcentaje": "92.94"},
    ]
    assert distribution_lines(None) == []


def test_campo_must_be_in_the_catalog():
    assert require_campo(3, {1, 2, 3, 4}) == 3
    with pytest.raises(HTTPException) as missing:
        require_campo(9, {1, 2, 3, 4})
    assert missing.value.status_code == 422


def test_usage_counts_payments_and_ignores_unknown_codes(cur):
    cur.execute("""
        SELECT btrim(cuartel_cc)
        FROM appsheet.tarjas_pagos
        WHERE btrim(COALESCE(cuartel_cc, '')) <> ''
        LIMIT 1
    """)
    code = cur.fetchone()[0]
    assert usage_count(cur, code) > 0
    assert usage_count(cur, "zz-test-cc-absent") == 0


def test_insert_keeps_name_and_leaves_odoo_empty_until_sync(cur):
    cur.execute("SELECT id_campo FROM appsheet.tarjas_campo ORDER BY id_campo LIMIT 1")
    campo = cur.fetchone()[0]
    code = "zz-test-cc"
    cur.execute(
        """
        INSERT INTO appsheet.tarjas_cc (id_cc, cultivo, id_campo)
        VALUES (%s, %s, %s)
        """,
        (code, "Huerto prueba", campo),
    )
    cur.execute(
        "SELECT cultivo, id_campo, valor_odoo FROM appsheet.tarjas_cc WHERE id_cc = %s",
        (code,),
    )
    assert cur.fetchone() == ("Huerto prueba", campo, None)

    cur.execute("SAVEPOINT dup")
    with pytest.raises(errors.UniqueViolation):
        cur.execute(
            """
            INSERT INTO appsheet.tarjas_cc (id_cc, cultivo, id_campo)
            VALUES (%s, %s, %s)
            """,
            (code, "Otro", campo),
        )
    cur.execute("ROLLBACK TO SAVEPOINT dup")

    cur.execute(
        """
        UPDATE appsheet.tarjas_cc
        SET cultivo = %s, id_campo = %s
        WHERE id_cc = %s
        """,
        ("Huerto nuevo", campo, code),
    )
    cur.execute(
        "SELECT cultivo FROM appsheet.tarjas_cc WHERE id_cc = %s",
        (code,),
    )
    assert cur.fetchone()[0] == "Huerto nuevo"
    assert usage_count(cur, code) == 0
