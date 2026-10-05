"""Monthly bonus of a tractorista lands under tipo_pago Tractorista."""

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


def test_bono_mensual_tractorista_writes_total_tractor(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT appsheet.costo_tractorista(
            'Felipe Cordova', 'Jornada Tractor normal', 9, DATE '2026-09-01'
        )
        """
    )
    assert int(cur.fetchone()[0]) == 72000

    cur.execute(
        """
        INSERT INTO appsheet.tarjas_bono_mensual (
            id_bono, trabajador, rut_trabajador, contratista,
            nombre_campo, id_cc, mes, monto, estado
        ) VALUES (
            't-bono-tract', 'Felipe Cordova', '1-9',
            'TEST TRACTORISTA BONO SPA', 'ZUÑIGA', '890',
            DATE '2099-01-01', 50000, 'Pendiente'
        )
        RETURNING id_resumen_pagos
        """
    )
    resumen = cur.fetchone()[0]
    cur.execute(
        """
        SELECT tipo_pago, labor, total_tractor, total_trabajado, total_pagar
        FROM appsheet.tarjas_pagos
        WHERE "id_Resumen" = %s
        """,
        (resumen,),
    )
    tipo, labor, tt, tw, tp = cur.fetchone()
    assert tipo == "Tractorista"
    assert labor == "Bono mensual"
    assert (int(tt), int(tw), int(tp)) == (50000, 50000, 50000)


def test_bono_mensual_non_tractorista_stays_bono(conn):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO appsheet.tarjas_bono_mensual (
            id_bono, trabajador, rut_trabajador, contratista,
            nombre_campo, id_cc, mes, monto, estado
        ) VALUES (
            't-bono-oper', 'Persona Sin Esquema Tractor', '2-7',
            'TEST OPERARIO BONO SPA', 'ZUÑIGA', '883',
            DATE '2099-02-01', 80000, 'Pendiente'
        )
        RETURNING id_resumen_pagos
        """
    )
    resumen = cur.fetchone()[0]
    cur.execute(
        """
        SELECT tipo_pago, labor, total_tractor, total_trabajado, total_pagar
        FROM appsheet.tarjas_pagos
        WHERE "id_Resumen" = %s
        """,
        (resumen,),
    )
    tipo, labor, tt, tw, tp = cur.fetchone()
    assert tipo == "Bono"
    assert labor == "Bono mensual"
    assert int(tt or 0) == 0
    assert (int(tw), int(tp)) == (80000, 80000)
