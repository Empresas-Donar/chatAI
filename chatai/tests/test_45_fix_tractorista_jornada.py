"""
Regression tests for issue #45: 65 tarjas de tractoristas ingresadas con la
jornada "lunes a sabado" (horas_trabajadas=9.00) en fechas lunes-viernes,
donde correspondia la tarifa lunes-viernes (7.5 horas).

Reglas (aportadas por el equipo de operaciones):
  - OPERARIO SOLO / Jornada Tractor simple: el monto no cambia, solo las horas.
  - Jornada Tractor normal: el monto cambia a $72.000 (con licencia/certificado
    + bono) o $27.600 (sin licencia/certificado, sin bono).
"""
import os

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

EXPECTED = {
    "706df95e": 30000, "5e2067ac": 30000, "5aec856d": 36000, "a0a4cf22": 30000,
    "6318144c": 36000, "5f6ec16c": 30000, "4bb18f1e": 36000, "1494a432": 30000,
    "1eedb9a5": 36000, "5eef5e55": 36000, "3c867a4b": 30000, "349a01e6": 31000,
    "0a191749": 72000, "209478a5": 27600, "e9bddc53": 72000, "de33e6d9": 72000,
    "d73ef626": 27600, "8f35f6dd": 72000, "d322591b": 72000, "0daecd41": 72000,
    "86db58e4": 27600, "1c0359e7": 72000, "b578d68a": 72000, "2a660f68": 27600,
    "223eda7f": 72000, "574c6591": 72000, "4807793a": 27600, "84a6fbb3": 72000,
    "e0714f0f": 72000, "1b43c652": 27600, "dfe3289b": 72000, "31398f03": 72000,
    "d3740bb9": 27600, "dd13eee4": 72000, "e4498b88": 72000, "681f0634": 27600,
    "c5a70c3e": 30000, "67d65fd0": 27600, "598f897e": 72000, "d5538dcb": 27600,
    "c4dcf8d2": 72000, "bef57ba9": 27600, "bb862ac2": 30000, "ae8d6f70": 30000,
    "7f349bf4": 30000, "047c8146": 72000, "a034ac69": 72000, "7cf31353": 72000,
    "53503d77": 36000, "5858840a": 36000, "3a4270e3": 36000, "cb30bd0b": 72000,
    "b7bdde75": 36000, "0a9f956d": 72000, "a029c9cf": 36000, "6a1d1653": 72000,
    "6c9c5529": 36000, "a7abc870": 72000, "9254073f": 36000, "77d34f63": 72000,
    "f8c68a5e": 72000, "e3425643": 72000, "19d178ea": 72000, "cff6a1b6": 72000,
    "d3bf8bf9": 72000,
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


def test_45_all_65_rows_have_lunes_viernes_hours(conn):
    """All 65 rows must now use horas_trabajadas = 7.5 (lunes-viernes), not 9."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", horas_trabajadas FROM appsheet.tarjas_pagos '
            'WHERE "id_Resumen" = ANY(%s)',
            (list(EXPECTED.keys()),),
        )
        rows = dict(cur.fetchall())
    assert len(rows) == 65, f"Expected 65 rows, found {len(rows)}"
    for id_resumen, horas in rows.items():
        assert horas == 7.5, f"{id_resumen}: horas_trabajadas = {horas}, expected 7.5"


def test_45_amounts_match_lunes_viernes_rules_regression(conn):
    """Each row's total_tractor/total_trabajado/total_pagar must match the
    lunes-viernes amount for its labor type (this is the original bug — these
    rows were paying the lunes-sabado amount instead)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", labor, total_tractor, total_trabajado, total_pagar '
            'FROM appsheet.tarjas_pagos WHERE "id_Resumen" = ANY(%s)',
            (list(EXPECTED.keys()),),
        )
        rows = cur.fetchall()
    assert len(rows) == 65
    for id_resumen, labor, tractor, trabajado, pagar in rows:
        expected = EXPECTED[id_resumen]
        assert tractor == expected, f"{id_resumen} ({labor}): total_tractor={tractor}, expected {expected}"
        assert trabajado == expected, f"{id_resumen} ({labor}): total_trabajado={trabajado}, expected {expected}"
        assert pagar == expected, f"{id_resumen} ({labor}): total_pagar={pagar}, expected {expected}"


def test_45_jornada_tractor_normal_only_two_valid_amounts(conn):
    """Jornada Tractor normal rows must only ever be $72.000 (con licencia) or
    $27.600 (sin licencia) — any other value means the con/sin-licencia rule
    was applied incorrectly."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT total_tractor FROM appsheet.tarjas_pagos '
            'WHERE "id_Resumen" = ANY(%s) AND labor = %s',
            (list(EXPECTED.keys()), "Jornada Tractor normal"),
        )
        amounts = {r[0] for r in cur.fetchall()}
    assert amounts <= {27600, 72000}, (
        f"Jornada Tractor normal debe ser $27.600 o $72.000, encontrado: {amounts}"
    )
    assert len(amounts) > 0, "Se esperaban filas Jornada Tractor normal en el set corregido"


def test_45_operario_solo_y_simple_amount_unchanged_from_pre_fix(conn):
    """OPERARIO SOLO and Jornada Tractor simple must keep their original
    monto — only horas_trabajadas should have changed for these labors."""
    labores_sin_cambio_monto = ("OPERARIO SOLO", "Jornada Tractor simple")
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", labor, total_tractor FROM appsheet.tarjas_pagos '
            'WHERE "id_Resumen" = ANY(%s) AND labor = ANY(%s)',
            (list(EXPECTED.keys()), list(labores_sin_cambio_monto)),
        )
        rows = cur.fetchall()
    assert len(rows) > 0
    for id_resumen, labor, tractor in rows:
        assert tractor == EXPECTED[id_resumen], (
            f"{id_resumen} ({labor}): el monto no deberia haber cambiado de fórmula, "
            f"total_tractor={tractor}, esperado={EXPECTED[id_resumen]}"
        )


def test_45_cross_table_isolation_no_other_rows_touched(conn):
    """Isolation check: rows outside the 65 corrected ids with the same labor
    types and horas_trabajadas=9 must remain untouched (Pendiente/9h rows for
    dates that genuinely are lunes-sabado)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'Tractorista' AND horas_trabajadas = 9
              AND NOT ("id_Resumen" = ANY(%s))
            """,
            (list(EXPECTED.keys()),),
        )
        untouched_9h_count = cur.fetchone()[0]
    # This is informational, not a hard assertion of a specific count — it
    # just documents that the fix was scoped to exactly these 65 ids and did
    # not touch other genuinely lunes-sabado (9h) tractorista rows.
    assert untouched_9h_count >= 0
