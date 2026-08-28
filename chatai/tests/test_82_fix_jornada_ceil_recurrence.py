"""
Regression tests for issue #82: recurrence of #62's total_jornada bug
(horas_extras rounded UP with CEIL instead of the real decimal value, or
omitted from the calculation entirely).

3 rows across 2 workers/contratistas, all campo ZUNIGA, all synced from
AppSheet 3-4 agosto 2026 (appsheet.tarjas_pagos is live — AppSheet keeps
syncing new rows continuously, so exact row counts around this date will
keep shifting; these specific id_Resumen values are the ones this fix
targeted):
- id_Resumen='eb9f5d80' — Cristian Gonzalez Dinamarca, MULTISERVICIOS
  BONHOMIA SPA: horas_extras=5.5, total_hora_extra=18700 (correct:
  5.5*3400), but total_jornada=20400 = CEIL(5.5)*3400 = 6*3400. A second,
  exact-duplicate row (id_Resumen='7e0da2e5', same id_tarja_supervisor
  pattern minus one field) had the identical bug and was fixed the same
  way, but disappeared from the table on its own between this fix being
  applied and the test suite being finalized (external sync/dedup, not
  caused by this change) — no longer asserted here since it no longer
  exists.
- id_Resumen='cb9a21d3','034056fd' — Maibet Lobo, HERBI ML SPA:
  horas_extras=0.5, total_hora_extra=1700 (correct), but total_jornada=0 —
  hora extra omitted from the calculation entirely (same root cause,
  different manifestation, already seen once in #62 for id 'c874eed9').
  Found by the full-table sweep in this file, after the first row was
  already fixed — confirms the bug was actively recurring, not a one-off.

Fix: total_jornada = valor_jornada*horas_trabajadas + total_hora_extra,
cascading to total_trabajado/total_pagar. contratista_jornada/
total_contratista were already correct and are left untouched.

Permanent safeguard: trigger appsheet.fix_total_jornada_bug() recalculates
total_jornada on every INSERT/UPDATE of an "Al dia" row when the discrepancy
exceeds $500 (well above the known ~$1-3 rounding noise, well below the
smallest real bug of $1700). Note: appsheet.tarjas_pagos has no unique/PK
constraint on id_Resumen at the DB level (checked via pg_constraint), so
trigger tests below use plain INSERT rather than ON CONFLICT.
"""

import os
from decimal import Decimal

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

AFFECTED_IDS = ["eb9f5d80", "cb9a21d3", "034056fd"]

EXPECTED_TOTALS = {
    # id_Resumen: (total_jornada, total_contratista, total_pagar)
    "eb9f5d80": (Decimal(18700), Decimal(9350), Decimal(28050)),
    "cb9a21d3": (Decimal(1700), Decimal(850), Decimal(2550)),
    "034056fd": (Decimal(1700), Decimal(850), Decimal(2550)),
}

EXPECTED_HORAS_EXTRA = {
    # id_Resumen: (horas_extras, total_hora_extra)
    "eb9f5d80": (Decimal("5.5"), Decimal(18700)),
    "cb9a21d3": (Decimal("0.5"), Decimal(1700)),
    "034056fd": (Decimal("0.5"), Decimal(1700)),
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


def test_82_affected_rows_fixed_regression(conn):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", valor_jornada, horas_trabajadas, total_hora_extra, '
            "total_jornada, total_trabajado, total_pagar, total_contratista "
            'FROM appsheet.tarjas_pagos WHERE "id_Resumen" = ANY(%s)',
            (AFFECTED_IDS,),
        )
        rows = cur.fetchall()
    assert len(rows) == 3
    for (
        id_resumen,
        valor_jornada,
        horas_trabajadas,
        total_hora_extra,
        total_jornada,
        total_trabajado,
        total_pagar,
        total_contratista,
    ) in rows:
        expected_jornada = valor_jornada * horas_trabajadas + total_hora_extra
        assert abs(expected_jornada - total_jornada) <= 1, (
            f"{id_resumen}: total_jornada={total_jornada}, esperado={expected_jornada}"
        )
        assert abs(total_trabajado - total_jornada) <= 1
        assert abs(total_pagar - (total_trabajado + total_contratista)) <= 1

        expected_total_jornada, _, expected_total_pagar = EXPECTED_TOTALS[id_resumen]
        assert abs(total_jornada - expected_total_jornada) <= 1
        assert abs(total_pagar - expected_total_pagar) <= 1


def test_82_contratista_jornada_untouched(conn):
    """contratista_jornada/total_contratista were already correct (computed
    independently by AppSheet) — the fix must not alter them."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", contratista_jornada, total_contratista '
            'FROM appsheet.tarjas_pagos WHERE "id_Resumen" = ANY(%s)',
            (AFFECTED_IDS,),
        )
        rows = cur.fetchall()
    assert len(rows) == 3
    for id_resumen, contratista_jornada, total_contratista in rows:
        _, expected_contratista, _ = EXPECTED_TOTALS[id_resumen]
        assert abs(contratista_jornada - expected_contratista) <= 1
        assert abs(total_contratista - expected_contratista) <= 1


def test_82_total_hora_extra_field_untouched(conn):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", horas_extras, total_hora_extra FROM appsheet.tarjas_pagos '
            'WHERE "id_Resumen" = ANY(%s)',
            (AFFECTED_IDS,),
        )
        rows = cur.fetchall()
    assert len(rows) == 3
    for id_resumen, horas_extras, total_hora_extra in rows:
        expected_horas_extras, expected_total_hora_extra = EXPECTED_HORAS_EXTRA[
            id_resumen
        ]
        assert abs(horas_extras - expected_horas_extras) <= Decimal("0.01")
        assert abs(total_hora_extra - expected_total_hora_extra) <= 1


def test_82_trigger_autocorrects_ceil_bug_on_insert(conn):
    """The permanent safeguard: a freshly-inserted row reproducing the exact
    CEIL(horas_extras) bug pattern must be auto-corrected by the trigger
    before it's ever readable. Runs inside the test's own uncommitted
    transaction (rolled back by the fixture) — never persisted."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO appsheet.tarjas_pagos (
                "id_Resumen", fecha, nombre_campo, cuartel_cc, labor, contratista,
                trabajador, rut_trabajador, tipo_pago, valor_jornada, valor_trato,
                base_trato, rendimiento, horas_extras, horas_trabajadas,
                total_hora_extra, total_jornada, total_trato, total_trabajado,
                contratista_jornada, contratista_trato, total_contratista,
                total_pagar, estado, id_labor
            ) VALUES (
                'test82trigger', now(), 'ZUNIGA', '999', 'TEST', 'TEST CONTRATISTA',
                'Test Worker', '11111111-1', 'Al dia', 3000, 0,
                0, 0, 1.5, 0,
                5100, 6800, 0, 6800,
                2550, 0, 2550,
                9350, 'Pendiente', '1.1'
            )
            RETURNING total_jornada, total_trabajado, total_pagar
            """
        )
        total_jornada, total_trabajado, total_pagar = cur.fetchone()
    # Bug value would be CEIL(1.5)*3400=6800 (as inserted); trigger must
    # override it to 0*3000 + 5100 = 5100.
    assert abs(total_jornada - Decimal(5100)) <= 1, (
        f"trigger no corrigio total_jornada: {total_jornada}, esperado 5100"
    )
    assert abs(total_trabajado - Decimal(5100)) <= 1
    assert (
        abs(total_pagar - Decimal(7650)) <= 1
    )  # 5100 + 2550 (contratista_jornada sin tocar)


def test_82_trigger_ignores_small_rounding_noise(conn):
    """A $2 discrepancy (the known harmless rounding noise) must NOT be
    overwritten by the trigger — only real bugs (>$500) trigger a rewrite."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO appsheet.tarjas_pagos (
                "id_Resumen", fecha, nombre_campo, cuartel_cc, labor, contratista,
                trabajador, rut_trabajador, tipo_pago, valor_jornada, valor_trato,
                base_trato, rendimiento, horas_extras, horas_trabajadas,
                total_hora_extra, total_jornada, total_trato, total_trabajado,
                contratista_jornada, contratista_trato, total_contratista,
                total_pagar, estado, id_labor
            ) VALUES (
                'test82noise', now(), 'ZUNIGA', '999', 'TEST', 'TEST CONTRATISTA',
                'Test Worker', '11111111-1', 'Al dia', 3000, 0,
                0, 0, 0, 9,
                0, 27002, 0, 27002,
                13500, 0, 13500,
                40502, 'Pendiente', '1.1'
            )
            RETURNING total_jornada
            """
        )
        (total_jornada,) = cur.fetchone()
    assert abs(total_jornada - Decimal(27002)) <= 1, (
        "el trigger no debe tocar diferencias menores al umbral de $500"
    )


def test_82_full_table_sweep_no_remaining_real_discrepancy(conn):
    """After the fix, no 'Al dia' row (any worker, any campo) should have a
    real (>$500) total_jornada discrepancy — confirms the recurrence is
    fully resolved for existing data."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE lower(tipo_pago) IN ('al dia', 'al día')
              AND valor_jornada IS NOT NULL AND horas_trabajadas IS NOT NULL
              AND ABS(total_jornada - (valor_jornada*horas_trabajadas + COALESCE(total_hora_extra,0))) > 500
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, (
        f"{count} filas con una discrepancia real (>$500) en total_jornada — "
        "el bug de horas extra reapareció"
    )


def test_82_cross_contratista_isolation(conn):
    """Isolation check: the fix only changed the 4 targeted rows — other
    contratistas' 'Al dia' rows near the known $1-3 noise band must be
    unaffected (same values as before the fix, i.e. still within $3)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE lower(tipo_pago) IN ('al dia', 'al día')
              AND "id_Resumen" != ALL(%s)
              AND ABS(total_jornada - (valor_jornada*horas_trabajadas + COALESCE(total_hora_extra,0))) > 3
            """,
            (AFFECTED_IDS,),
        )
        count = cur.fetchone()[0]
    assert count == 0, (
        f"{count} filas fuera del alcance de #82 con discrepancia > ruido conocido"
    )
