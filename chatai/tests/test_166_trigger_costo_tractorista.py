"""Tractorista cost is calculated in Postgres, not in AppSheet."""

import os

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)


@pytest.fixture
def conn():
    c = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    yield c
    c.rollback()
    c.close()


def test_166_trigger_is_enabled(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tgenabled::text
        FROM pg_trigger
        WHERE tgname = 'trg_costo_tractorista'
          AND tgrelid = 'appsheet.tarjas_pagos'::regclass
        """
    )
    row = cur.fetchone()
    assert row is not None, "trg_costo_tractorista is not installed"
    assert row[0] == "O"


def test_166_costo_matches_tariff(conn):
    cur = conn.cursor()
    cases = [
        ("Felipe Cordova", "Jornada Tractor normal", 9, "2026-09-01", 72000),
        ("Cristian Gonzalez", "Jornada Tractor normal", 9, "2026-09-01", 66000),
        ("Cristian Gonzalez", "Jornada Tractor normal", 7.5, "2026-08-03", 55000),
        ("Cristian Gonzalez", "Jornada Tractor normal", 4.5, "2026-08-06", 33000),
        ("Felipe Cordova", "Jornada Tractor normal", 7.5, "2026-09-07", 61000),
        ("Felipe Cordova", "Jornada Tractor normal", 4.5, "2026-09-25", 39000),
        ("Cristian Gonzalez", "Hora Extra", 2, "2026-09-03", 6800),
        ("Cristian Gonzalez", "Hora Extra", 4.5, "2026-09-05", 15300),
        ("Operario Fundo", "Jornada Tractor normal", 9, "2026-09-15", 27600),
        ("Operario Fundo", "Jornada Tractor normal", 7.5, "2026-09-04", 23000),
        ("Operario Fundo", "Jornada Tractor normal", 4.5, "2026-09-14", 13800),
        ("Operario Fundo", "jornada tractor Gilberto (sin tractor)", 9, "2026-08-05", 25000),
        ("Operario Fundo", "Jornada Tractor Chico (sin operador)", 9, "2026-09-01", 25000),
        ("Felipe Cordova", "OPERARIO SOLO", 9, "2026-09-01", 60000),
        ("Felipe Cordova", "Labor Extraordinaria", 9, "2026-09-01", 10000),
    ]
    for trabajador, labor, horas, fecha, expected in cases:
        cur.execute(
            "SELECT appsheet.costo_tractorista(%s, %s, %s, %s::date)",
            (trabajador, labor, horas, fecha),
        )
        got = int(cur.fetchone()[0])
        assert got == expected, f"{trabajador} {labor} {horas}h -> {got}, expected {expected}"


def test_166_trigger_ignores_non_tractorista(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT "id_Resumen", tipo_pago
        FROM appsheet.tarjas_pagos
        WHERE lower(trim(COALESCE(tipo_pago, ''))) IS DISTINCT FROM 'tractorista'
        LIMIT 1
        """
    )
    row_id, tipo = cur.fetchone()
    cur.execute(
        """
        UPDATE appsheet.tarjas_pagos
        SET total_tractor = 12345,
            labor = 'Jornada Tractor normal',
            horas_trabajadas = 9,
            fecha = fecha
        WHERE "id_Resumen" = %s
        RETURNING total_tractor, tipo_pago
        """,
        (row_id,),
    )
    tt, tipo_after = cur.fetchone()
    assert int(tt) == 12345
    assert tipo_after == tipo


def test_166_manual_payment_is_kept_when_the_day_does_not_change(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT "id_Resumen"
        FROM appsheet.tarjas_pagos
        WHERE lower(trim(tipo_pago)) = 'tractorista'
          AND total_tractor = 72000
        LIMIT 1
        """
    )
    row_id = cur.fetchone()[0]
    cur.execute(
        """
        UPDATE appsheet.tarjas_pagos
        SET total_pagar = 50000,
            fecha = fecha
        WHERE "id_Resumen" = %s
        RETURNING total_tractor, total_trabajado, total_pagar
        """,
        (row_id,),
    )
    tt, tw, tp = cur.fetchone()
    assert (tt, tw, tp) == (50000, 50000, 50000)

    cur.execute(
        """
        UPDATE appsheet.tarjas_pagos
        SET horas_trabajadas = 9
        WHERE "id_Resumen" = %s
          AND horas_trabajadas = 9
        RETURNING total_tractor
        """,
        (row_id,),
    )
    # Same hours: still a manual amount, because the day did not change.
    assert int(cur.fetchone()[0]) == 50000

    cur.execute(
        """
        UPDATE appsheet.tarjas_pagos
        SET horas_trabajadas = 4.5
        WHERE "id_Resumen" = %s
        RETURNING total_tractor, total_trabajado, total_pagar
        """,
        (row_id,),
    )
    tt, tw, tp = cur.fetchone()
    assert (int(tt), int(tw), int(tp)) == (39000, 39000, 39000)


def test_166_other_campo_same_day_is_not_a_duplicate(conn):
    cur = conn.cursor()
    rows = [
        ("t166-isla", "ISLA DE MAIPO", "400", 25000),
        ("t166-tala", "TALAGANTE", "616", 25000),
        ("t166-dup", "ISLA DE MAIPO", "400", 0),
    ]
    for row_id, campo, cc, expected in rows:
        cur.execute(
            """
            INSERT INTO appsheet.tarjas_pagos (
                "id_Resumen", fecha, trabajador, labor, horas_trabajadas,
                tipo_pago, nombre_campo, cuartel_cc, total_tractor
            ) VALUES (
                %s, '12/31/2098 00:00:00', 'Operario Fundo',
                'Jornada Tractor simple', 9, 'Tractorista', %s, %s, 0
            )
            RETURNING total_tractor
            """,
            (row_id, campo, cc),
        )
        got = int(cur.fetchone()[0])
        assert got == expected, f"{campo} {cc} -> {got}, expected {expected}"
