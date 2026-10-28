"""Editing supervisor hours recalculates the Al día amount on tarjas_pagos."""

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


def _seed(cur, sup_id, pago_id, horas_sup, horas_pago, valor, total, contratista):
    cur.execute(
        """
        INSERT INTO appsheet.tarjas_supervisor (id_supervisor, fecha, horas_trabajadas)
        VALUES (%s, '2099-12-31 00:00:00', %s)
        """,
        (sup_id, horas_sup),
    )
    cur.execute(
        """
        INSERT INTO appsheet.tarjas_det_supervisor (id_detalle, id_supervisor)
        VALUES (%s, %s)
        """,
        (pago_id, sup_id),
    )
    cur.execute(
        """
        INSERT INTO appsheet.tarjas_pagos (
            "id_Resumen", fecha, trabajador, tipo_pago, horas_trabajadas,
            valor_jornada, total_jornada, total_trabajado,
            total_contratista, contratista_jornada, total_pagar, estado
        ) VALUES (
            %s, '12/31/2099 00:00:00', 'Test Horas', 'Al dia', %s,
            %s, %s, %s, %s, %s, 0, 'Pendiente'
        )
        """,
        (pago_id, horas_pago, valor, total, total, contratista, contratista),
    )


def _totals(cur, pago_id):
    cur.execute(
        """
        SELECT horas_trabajadas, total_jornada, total_trabajado,
               total_contratista, contratista_jornada, total_pagar
        FROM appsheet.tarjas_pagos
        WHERE "id_Resumen" = %s
        """,
        (pago_id,),
    )
    return cur.fetchone()


def test_167_trigger_is_enabled(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tgenabled::text
        FROM pg_trigger
        WHERE tgname = 'trg_sync_horas_supervisor'
          AND tgrelid = 'appsheet.tarjas_supervisor'::regclass
        """
    )
    row = cur.fetchone()
    assert row is not None, "trg_sync_horas_supervisor is not installed"
    assert row[0] == "O"


def test_167_supervisor_hour_change_recalculates_jornada(conn):
    cur = conn.cursor()
    _seed(cur, "t167-sup", "t167-pago", "75", 75, "2933.333333333", 220000, 110000)

    cur.execute(
        """
        UPDATE appsheet.tarjas_supervisor
           SET horas_trabajadas = '7.5'
         WHERE id_supervisor = 't167-sup'
        """
    )
    horas, jornada, trabajado, contratista, c_jornada, pagar = _totals(cur, "t167-pago")
    assert float(horas) == 7.5
    assert int(jornada) == 22000
    assert int(trabajado) == 22000
    assert int(contratista) == 11000
    assert int(c_jornada) == 11000
    assert int(pagar) == 0


def test_167_comma_hours_on_scaled_rate_are_left_alone(conn):
    """7,5 stored as 75 with the rate already divided must not drop the day to $2.200."""
    cur = conn.cursor()
    _seed(cur, "t167-sup-scaled", "t167-pago-scaled", "7,5", 75, "293.333333333", 22000, 11000)

    cur.execute(
        """
        UPDATE appsheet.tarjas_supervisor
           SET horas_trabajadas = '8'
         WHERE id_supervisor = 't167-sup-scaled'
        """
    )
    horas, jornada, _, contratista, _, _ = _totals(cur, "t167-pago-scaled")
    assert float(horas) == 75
    assert int(jornada) == 22000
    assert int(contratista) == 11000
