"""
Regression tests for issue #62: total_jornada was computed using horas_extras
rounded UP to the next whole number (CEIL) instead of the real decimal value,
even though horas_extras and total_hora_extra themselves were already correct.

Confirmed with a real payroll report: Rodolfo Henriquez Ahumada, 29 julio
2026 (id_Resumen='310c0ca1') worked 7h + 1.5h extra at $3.000/h base and
$3.400/h extra. Expected total_jornada = 21000 + 5100 = 26100, but the
system had 27800 (using 2h extra -> 6800 instead of 5100).

Fix: total_jornada = valor_jornada * horas_trabajadas + total_hora_extra,
using the already-correct total_hora_extra field directly instead of
recomputing from a rounded horas_extras. Cascades to total_trabajado,
contratista_jornada (50% markup, verified for both affected contratistas),
total_contratista, total_pagar.
"""
import os
from decimal import Decimal

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

AFFECTED_IDS = [
    "16eccd9b", "310c0ca1", "450ec1be", "5b83dae2", "5fa724ad",
    "7ba0e631", "85815048", "8fa5ce28", "9d4de9d6", "ada92a84",
    "ccadf008", "d842f9a0",
]


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


def test_62_total_jornada_uses_real_total_hora_extra_regression(conn):
    """total_jornada must equal valor_jornada*horas_trabajadas + total_hora_extra
    for the 12 affected rows — not the CEIL(horas_extras)*3400 bug value."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", valor_jornada, horas_trabajadas, total_hora_extra, total_jornada '
            'FROM appsheet.tarjas_pagos WHERE "id_Resumen" = ANY(%s)',
            (AFFECTED_IDS,),
        )
        rows = cur.fetchall()
    assert len(rows) == 12
    for id_resumen, valor_jornada, horas_trabajadas, total_hora_extra, total_jornada in rows:
        expected = valor_jornada * horas_trabajadas + total_hora_extra
        assert abs(expected - total_jornada) <= 1, (
            f"{id_resumen}: total_jornada={total_jornada}, esperado={expected}"
        )


def test_62_rodolfo_henriquez_specific_case_regression(conn):
    """The exact case reported: Rodolfo's 7h + 1.5h-extra record must total
    $26,100, so combined with his other same-day record (2h, $6,000,
    unaffected) the full day is $27,000 jornada + $5,100 extra = $32,100."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT total_jornada, total_trabajado FROM appsheet.tarjas_pagos '
            'WHERE "id_Resumen" = \'310c0ca1\''
        )
        total_jornada, total_trabajado = cur.fetchone()
        cur.execute(
            'SELECT total_jornada FROM appsheet.tarjas_pagos '
            "WHERE \"id_Resumen\" = '60eef862'"
        )
        other_record_jornada = cur.fetchone()[0]
    assert abs(total_jornada - Decimal("26100")) <= 1
    assert abs(total_trabajado - Decimal("26100")) <= 1
    combined_day_total = total_jornada + other_record_jornada
    assert abs(combined_day_total - Decimal("32100")) <= 1, (
        f"Total del día combinado={combined_day_total}, esperado=32100 "
        f"($27.000 jornada + $5.100 hora extra)"
    )


def test_62_contratista_jornada_markup_still_50_percent(conn):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT total_jornada, contratista_jornada FROM appsheet.tarjas_pagos '
            'WHERE "id_Resumen" = ANY(%s)',
            (AFFECTED_IDS,),
        )
        rows = cur.fetchall()
    assert len(rows) == 12
    for total_jornada, contratista_jornada in rows:
        expected = round(total_jornada * Decimal("0.5"))
        assert abs(expected - contratista_jornada) <= 1


def test_62_total_hora_extra_field_untouched(conn):
    """The fix must not have altered horas_extras/total_hora_extra — those
    were already correct; only total_jornada (and its cascade) changed."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "id_Resumen", horas_extras, total_hora_extra FROM appsheet.tarjas_pagos '
            'WHERE "id_Resumen" = ANY(%s)',
            (AFFECTED_IDS,),
        )
        rows = cur.fetchall()
    for id_resumen, horas_extras, total_hora_extra in rows:
        expected_total = horas_extras * 3400
        assert abs(expected_total - total_hora_extra) <= 1, (
            f"{id_resumen}: total_hora_extra should remain horas_extras*3400"
        )


def test_62_cross_campo_isolation_only_zuniga_affected(conn):
    """Isolation check: this bug (and its fix) only occurred in Zuñiga —
    other campos must not have any row matching the same CEIL pattern."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE lower(tipo_pago) IN ('al dia', 'al día') AND horas_extras > 0
              AND nombre_campo != 'ZUÑIGA'
              AND ABS(total_jornada - (valor_jornada*horas_trabajadas + CEIL(horas_extras)*3400)) < 1
              AND horas_extras != CEIL(horas_extras)
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, f"{count} filas fuera de Zuñiga con el mismo patrón sin corregir"
