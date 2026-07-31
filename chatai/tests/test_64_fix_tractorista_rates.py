"""
Regression tests for issue #64: tractorista payment amounts did not
correspond to the correct rate for each worker.

Rate catalog: appsheet.tarjas_labor (valor_c_operador_lunes_viernes /
valor_s_operador_lunes_viernes / *_lunes_sabado columns) — not derivable
from the code, only from the DB:
    Jornada Tractor normal: con operador L-V = 66000, sin operador L-V = 27600
    OPERARIO SOLO:          flat 30000 in all 4 combinations (no bono)

The $6.000 bono is PER WORKER (appsheet.tarjas_personal.licencia_clase_d and
certificado_sag, both 'SI'), not per machine:
    ANDRES DIAZ HERRRRA:              licencia_clase_d='NO', certificado_sag='NO' -> no bono
    LUIS IVAN CONTRERAS PERALTA / NIVALDO MALDONADO VALENZUELA: both 'SI'  -> +6000 bono

Root cause: Andres Diaz's "Jornada Tractor normal" rows were using the
sin_operador_lunes_viernes column ($27.600) instead of con_operador sin
bono ($66.000). Two Saturday rows (Luis Ivan / Nivaldo, 11/07/2026) were
using the lunes-sabado column with bono ($61.000) instead of lunes-viernes
with bono ($72.000). One incomplete row (Luis Ivan, 03/07/2026,
horas_trabajadas=1, total=0) was confirmed by the user as a worked day and
corrected the same way. Business rule confirmed by the user: hours do not
factor into the amount and every tractorista row should use
horas_trabajadas=9 and the lunes-viernes rate column, regardless of the
actual calendar day.
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


def test_64_all_tractorista_rows_have_9_hours_regression(conn):
    """horas_trabajadas must be 9 for every Tractorista row — the rate does
    not depend on hours worked."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'Tractorista' AND horas_trabajadas != 9
            """
        )
        (bad_count,) = cur.fetchone()
    assert bad_count == 0


def test_64_andres_diaz_jornada_tractor_normal_no_bono_regression(conn):
    """Andres Diaz does not qualify for the 6000 bono (licencia_clase_d='NO',
    certificado_sag='NO') so his 'Jornada Tractor normal' rows must be
    con_operador_lunes_viernes without bono: $66.000, not the $27.600
    sin_operador value nor the $72.000 con-bono value his coworkers get."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT total_tractor, total_trabajado, total_pagar, count(*)
            FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'Tractorista'
              AND labor = 'Jornada Tractor normal'
              AND trabajador LIKE 'ANDR%S D%AZ HERRRRA'
            GROUP BY total_tractor, total_trabajado, total_pagar
            """
        )
        rows = cur.fetchall()
    assert len(rows) == 1, f"expected a single uniform amount, got {rows}"
    total_tractor, total_trabajado, total_pagar, count = rows[0]
    assert total_tractor == 66000
    assert total_trabajado == 66000
    assert total_pagar == 66000
    assert count == 12


def test_64_luis_ivan_nivaldo_jornada_tractor_normal_with_bono_regression(conn):
    """Luis Ivan and Nivaldo both qualify for the bono (licencia_clase_d='SI',
    certificado_sag='SI'): every 'Jornada Tractor normal' row for either of
    them must be $72.000 — including the two Saturday rows that were stuck
    at the lunes-sabado rate ($61.000) and the one incomplete row that was
    at $0."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trabajador, total_tractor, count(*)
            FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'Tractorista'
              AND labor = 'Jornada Tractor normal'
              AND (trabajador LIKE 'LUIS IV%N CONTRERAS PERALTA'
                   OR trabajador LIKE 'NIVALDO MALDONADO VALENZUELA')
            GROUP BY trabajador, total_tractor
            """
        )
        rows = cur.fetchall()
    by_worker = {}
    for trabajador, total, count in rows:
        by_worker.setdefault(trabajador, []).append(total)
    assert len(by_worker) == 2
    for trabajador, totals in by_worker.items():
        assert totals == [72000], f"{trabajador} has a non-72000 row: {totals}"


def test_64_operario_solo_bono_by_worker_qualification_regression(conn):
    """OPERARIO SOLO has no machine, so the bono is granted purely on the
    worker's personal qualification: Andres Diaz (no bono) stays at $30.000,
    Luis Ivan / Nivaldo (bono) stay at $36.000 — this was already correct
    before this fix and must not be touched."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trabajador, total_tractor, count(*)
            FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'Tractorista' AND labor = 'OPERARIO SOLO'
            GROUP BY trabajador, total_tractor
            """
        )
        rows = {trabajador: total for trabajador, total, _ in cur.fetchall()}
    andres = next(v for k, v in rows.items() if "D" in k and "AZ HERRRRA" in k)
    luis = next(v for k, v in rows.items() if "CONTRERAS PERALTA" in k)
    nivaldo = next(v for k, v in rows.items() if "MALDONADO VALENZUELA" in k)
    assert andres == 30000
    assert luis == 36000
    assert nivaldo == 36000


def test_64_total_trabajado_and_total_pagar_mirror_total_tractor_regression(conn):
    """total_trabajado and total_pagar must always mirror total_tractor for
    Tractorista rows (contratista_jornada/contratista_trato/total_contratista
    are always 0 for this tipo_pago)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'Tractorista'
              AND (total_trabajado != total_tractor OR total_pagar != total_tractor)
            """
        )
        (bad_count,) = cur.fetchone()
    assert bad_count == 0


def test_64_jornada_tractor_simple_untouched_isolation(conn):
    """Jornada Tractor simple (only Nivaldo, 1 row) already matched the
    catalog (25000 con operador + 6000 bono = 31000) and must not have been
    touched by this fix."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT total_tractor, horas_trabajadas FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'Tractorista' AND labor = 'Jornada Tractor simple'
            """
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    total_tractor, horas = rows[0]
    assert total_tractor == 31000
    assert horas == 9


def test_64_no_other_tipo_pago_rows_touched_isolation(conn):
    """This fix must only affect tipo_pago='Tractorista' rows — 'trato' and
    'Al dia' rows must be unaffected."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'Tractorista'
            """
        )
        (tractorista_count,) = cur.fetchone()
    assert tractorista_count == 69
