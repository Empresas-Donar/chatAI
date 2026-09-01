"""
Regression tests for issue #73: appsheet.tarjas_maquina was replaced with a
new schema (color, patente, tractorista, campo columns added) and new data
(18 rows across 3 campos, provided by the user).

The table had no PK before this change and the same id_maquina can now
appear more than once (one row per campo where that machine is deployed),
so (id_maquina, campo) is the natural unique key of the new data -
verified before writing sql/tarjas/16_replace_tarjas_maquina.sql.

Known, deliberately-preserved data inconsistency (not a bug in this
migration): id_maquina '3aa5e989' is named "Massey Ferguson 250" in campo
1/2 but "Massey 265" in campo 3 - this came from the user's own source
table as-is and was flagged back to them, not silently "fixed".
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


def test_73_new_columns_exist(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='appsheet' AND table_name='tarjas_maquina'
            """
        )
        cols = {r[0] for r in cur.fetchall()}
    for expected in ("color", "patente", "tractorista", "campo"):
        assert expected in cols


def test_73_row_count_is_18_regression(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM appsheet.tarjas_maquina")
        (count,) = cur.fetchone()
    assert count == 18


def test_73_id_maquina_campo_is_unique_regression(conn):
    """id_maquina alone is no longer unique (a machine can be deployed to
    several campos) - but (id_maquina, campo) must be."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id_maquina, campo, count(*) FROM appsheet.tarjas_maquina
            GROUP BY id_maquina, campo HAVING count(*) > 1
            """
        )
        dupes = cur.fetchall()
    assert dupes == []


def test_73_campo_1_has_five_and_campo_2_has_four_machines_regression(conn):
    """Campo 2 has the same 4 machines as campo 1 (Farmtrac, Massey
    Ferguson 250, Same frutteto 80.4, Same frutetto 70) minus 'Same
    Frutteto 65' (VPYY10), which campo 1 has and campo 2 does not."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id_maquina FROM appsheet.tarjas_maquina WHERE campo='1' ORDER BY id_maquina"
        )
        campo1 = {r[0] for r in cur.fetchall()}
        cur.execute(
            "SELECT id_maquina FROM appsheet.tarjas_maquina WHERE campo='2' ORDER BY id_maquina"
        )
        campo2 = {r[0] for r in cur.fetchall()}
    assert len(campo1) == 5
    assert len(campo2) == 4
    assert campo2 < campo1
    assert campo1 - campo2 == {"c520d028"}


def test_73_campo_3_has_nine_machines_regression(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM appsheet.tarjas_maquina WHERE campo='3'")
        (count,) = cur.fetchone()
    assert count == 9


def test_73_new_machine_ids_present_regression(conn):
    """48d46934 and 3aa5e990 are new, distinct machine ids confirmed by the
    user (not typos of the pre-existing 48d46933 / 3aa5e989)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id_maquina FROM appsheet.tarjas_maquina WHERE id_maquina IN (%s, %s)",
            ("48d46934", "3aa5e990"),
        )
        found = {r[0] for r in cur.fetchall()}
    assert found == {"48d46934", "3aa5e990"}


def test_73_blank_cumple_stored_as_null_regression(conn):
    """Rows with a blank 'Cumple' cell in the source (patentes RLXJ64 and
    SJWB50) must be stored as NULL, not as an empty string or a guessed
    default."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT patente, cumple FROM appsheet.tarjas_maquina WHERE patente IN (%s, %s)",
            ("RLXJ64", "SJWB50"),
        )
        rows = dict(cur.fetchall())
    assert rows["RLXJ64"] is None
    assert rows["SJWB50"] is None
