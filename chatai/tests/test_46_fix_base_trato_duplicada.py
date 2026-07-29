"""
Regression tests for issue #46: 60 tarjas de tipo trato tenian base_trato
asignada mas de una vez el mismo dia cuando el trabajador realizo varias
labores de trato en la misma jornada -- la base solo corresponde a la
primera labor del dia.

Fix: base_trato=0 en las labores duplicadas, total_trato recalculado como
rendimiento*valor_trato (formula confirmada en issue #42), y
total_trabajado / total_contratista (~45% markup) / total_pagar
recalculados en consecuencia.
"""
import os
from decimal import Decimal

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# id_Resumen -> (total_trato, total_trabajado, total_contratista, total_pagar)
EXPECTED = {
    "9ce21206": (3000, 3000, 1350, 4350), "3b2e75ac": (3000, 3000, 1350, 4350),
    "f339c06d": (45, 45, 20, 45), "95630a0d": (45, 45, 20, 45),
    "efa2c06d": (3000, 3000, 1350, 4350), "f3a36a08": (45, 45, 20, 45),
    "14dfc372": (45, 45, 20, 45), "428d110b": (3000, 3000, 1350, 4350),
    "0662dece": (45, 45, 20, 45), "e3dba9f2": (3000, 3000, 1350, 4350),
    "f8985f05": (45, 45, 20, 45), "922e6cf1": (45, 45, 20, 45),
    "5cdf15d6": (45, 45, 20, 45), "7ddf2705": (45, 45, 20, 45),
    "59f14f1d": (45, 45, 20, 45), "2a9fec5d": (45, 45, 20, 45),
    "fb4d8a70": (45, 45, 20, 45), "6038d8ca": (45, 45, 20, 45),
    "3683cfbc": (45, 45, 20, 45), "4ff5e122": (3000, 3000, 1350, 4350),
    "6b1d7735": (3000, 3000, 1350, 4350), "6ab164f8": (3000, 3000, 1350, 4350),
    "93993452": (3000, 3000, 1350, 4350), "a94c801d": (3000, 3000, 1350, 4350),
    "6c004cec": (3000, 3000, 1350, 4350), "9e72623e": (3000, 3000, 1350, 4350),
    "499432df": (3000, 3000, 1350, 4350), "c9243a96": (10500, 10500, 4725, 15225),
    "820b8552": (10000, 10000, 4500, 14500), "e5b6a269": (10500, 10500, 4725, 15225),
    "fff23482": (15000, 15000, 6750, 21750), "b95899e9": (10000, 10000, 4500, 14500),
    "d34b22a8": (10000, 10000, 4500, 14500), "9d198a66": (7500, 7500, 3375, 10875),
    "09c88c90": (7500, 7500, 3375, 10875), "91824755": (7500, 7500, 3375, 10875),
    "8bbe432e": (7500, 7500, 3375, 10875), "32758f8e": (9000, 9000, 4050, 13050),
    "64bef651": (9000, 9000, 4050, 13050), "9c1e18fa": (9750, 9750, 4388, 14138),
    "2fc8adb6": (9750, 9750, 4388, 14138), "03c039d6": (9000, 9000, 4050, 13050),
    "a16f13fc": (45, 45, 20, 45), "bb6b8559": (7500, 7500, 3375, 10875),
    "c869af22": (7500, 7500, 3375, 10875), "9d6ad59e": (20000, 20000, 9000, 29000),
    "a691281c": (20000, 20000, 9000, 29000), "01bc8a64": (7500, 7500, 3375, 10875),
    "36e7ec80": (16500, 16500, 7425, 23925), "10350369": (2500, 2500, 1125, 3625),
    "2ec25728": (20000, 20000, 9000, 29000), "6a302cc1": (20000, 20000, 9000, 29000),
    "2d96a5d3": (20000, 20000, 9000, 29000), "8e010fa9": (20000, 20000, 9000, 29000),
    "a131b6c7": (9000, 9000, 4050, 13050), "6fc97b4b": (9000, 9000, 4050, 13050),
    "3391b76a": (12500, 12500, 5625, 18125), "0a24acfe": (12500, 12500, 5625, 18125),
    "10419f26": (10000, 10000, 4500, 14500), "c0ca9d8a": (10000, 10000, 4500, 14500),
}


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


def test_46_all_60_rows_have_base_trato_zero(conn):
    """The duplicated base_trato must be removed (set to 0) in all 60 rows."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", base_trato FROM appsheet.tarjas_pagos '
            'WHERE "id_Resumen" = ANY(%s)',
            (list(EXPECTED.keys()),),
        )
        rows = dict(cur.fetchall())
    assert len(rows) == 60, f"Expected 60 rows, found {len(rows)}"
    for id_resumen, base in rows.items():
        assert base == 0, f"{id_resumen}: base_trato = {base}, expected 0"


def test_46_recalculated_amounts_match_regression(conn):
    """total_trato/total_trabajado/total_contratista/total_pagar must match
    the recalculated values (rendimiento*valor_trato, without the duplicated
    base_trato) — this is the original bug being fixed."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", total_trato, total_trabajado, total_contratista, total_pagar '
            'FROM appsheet.tarjas_pagos WHERE "id_Resumen" = ANY(%s)',
            (list(EXPECTED.keys()),),
        )
        rows = cur.fetchall()
    assert len(rows) == 60
    for id_resumen, trato, trabajado, contratista, pagar in rows:
        exp_trato, exp_trabajado, exp_contratista, exp_pagar = EXPECTED[id_resumen]
        assert trato == exp_trato, f"{id_resumen}: total_trato={trato}, expected {exp_trato}"
        assert trabajado == exp_trabajado, f"{id_resumen}: total_trabajado={trabajado}, expected {exp_trabajado}"
        assert contratista == exp_contratista, f"{id_resumen}: total_contratista={contratista}, expected {exp_contratista}"
        assert pagar == exp_pagar, f"{id_resumen}: total_pagar={pagar}, expected {exp_pagar}"


def test_46_total_trato_matches_rendimiento_times_valor_trato_formula(conn):
    """With base_trato=0, total_trato must equal exactly rendimiento*valor_trato
    (the formula confirmed in issue #42), not some other stale value."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", rendimiento, valor_trato, total_trato '
            'FROM appsheet.tarjas_pagos WHERE "id_Resumen" = ANY(%s)',
            (list(EXPECTED.keys()),),
        )
        rows = cur.fetchall()
    assert len(rows) == 60
    for id_resumen, rendimiento, valor_trato, total_trato in rows:
        expected = (rendimiento or Decimal(0)) * (valor_trato or Decimal(0))
        assert abs(expected - total_trato) <= 1, (
            f"{id_resumen}: total_trato={total_trato}, rendimiento*valor_trato={expected}"
        )


def test_46_contratista_markup_still_approximately_45_percent(conn):
    """total_contratista should still be ~45% of the recalculated total_trato
    (the markup rate itself wasn't part of this bug — only the duplicated
    base_trato was)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", total_trato, total_contratista '
            'FROM appsheet.tarjas_pagos WHERE "id_Resumen" = ANY(%s)',
            (list(EXPECTED.keys()),),
        )
        rows = cur.fetchall()
    assert len(rows) == 60
    for id_resumen, total_trato, total_contratista in rows:
        expected_markup = round(total_trato * Decimal("0.45"))
        assert abs(expected_markup - total_contratista) <= 1, (
            f"{id_resumen}: total_contratista={total_contratista}, "
            f"~45% de total_trato={expected_markup}"
        )


def test_46_contratista_trato_synced_with_total_contratista_regression(conn):
    """Regression: updating total_contratista without also updating
    contratista_trato re-breaks the sync fixed in issue #42. contratista_jornada
    is 0 in all 60 rows (trato-only), so contratista_trato must equal
    total_contratista exactly."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", contratista_jornada, contratista_trato, total_contratista '
            'FROM appsheet.tarjas_pagos WHERE "id_Resumen" = ANY(%s)',
            (list(EXPECTED.keys()),),
        )
        rows = cur.fetchall()
    assert len(rows) == 60
    for id_resumen, contratista_jornada, contratista_trato, total_contratista in rows:
        assert contratista_jornada == 0, f"{id_resumen}: contratista_jornada={contratista_jornada}, expected 0"
        assert contratista_trato == total_contratista, (
            f"{id_resumen}: contratista_trato={contratista_trato} != "
            f"total_contratista={total_contratista} (issue #42 regression)"
        )


def test_46_cross_table_isolation_only_tarjas_pagos_touched(conn):
    """Isolation check: the fix must not have altered tarjas_labores or
    tarjas_cc — this was a tarjas_pagos-only data correction."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema = 'appsheet' AND table_name = 'tarjas_labores'
              AND column_name IN ('base_trato', 'total_contratista')
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, (
        "tarjas_labores unexpectedly has base_trato/total_contratista columns "
        "— schema drift, check migration scope"
    )
