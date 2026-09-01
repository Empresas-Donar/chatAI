"""
Regression tests for issue #140: el reporte Tarjas -> Detalle Operacional
mostraba "-" en Costo/hora cuando una labor se pagaba 100% como hora extra
(horas_trabajadas=0, horas_extras>0), porque solo sumaba horas_trabajadas.
"""

import decimal
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


def test_140_tarjas_reporte_view_has_horas_extras_column(conn):
    """tarjas_reporte debe exponer horas_extras (issue #140)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'appsheet'
              AND table_name = 'tarjas_reporte'
              AND column_name = 'horas_extras'
            """
        )
        row = cur.fetchone()
    assert row is not None, "horas_extras not found in appsheet.tarjas_reporte"
    assert row[0] == "numeric"


def test_140_costo_hora_not_null_when_only_horas_extras(conn):
    """
    Regression: una labor pagada 100% como hora extra (horas_trabajadas=0,
    horas_extras>0) debe producir un costo_hora calculado, no NULL.
    Reproduce el caso real: HERBI ML SPA / ZUNIGA / APERTURA-CERRADO TECHOS.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                SUM(horas_trabajadas) AS horas_trabajadas,
                SUM(horas_extras)     AS horas_extras,
                SUM(total_labor)      AS costo_total,
                CASE WHEN SUM(horas_trabajadas) + SUM(horas_extras) > 0
                     THEN ROUND((SUM(total_labor)
                          / (SUM(horas_trabajadas) + SUM(horas_extras)))::numeric, 0)
                     ELSE NULL END AS costo_hora
            FROM appsheet.tarjas_reporte
            WHERE contratista = 'HERBI ML SPA'
              AND nombre_campo ILIKE '%iga'
              AND "CC" = '878'
              AND fecha BETWEEN '2026-08-19' AND '2026-08-25'
            GROUP BY tipo_pago, "Nombre Labor", "CC"
            """
        )
        row = cur.fetchone()
    assert row is not None, (
        "No matching rows for the regression case — data may have changed"
    )
    horas_trabajadas, horas_extras, costo_total, costo_hora = row
    assert horas_trabajadas == 0, (
        "Regression fixture assumes horas_trabajadas=0 for this row"
    )
    assert horas_extras > 0, "Regression fixture assumes horas_extras>0 for this row"
    assert costo_hora is not None, (
        "costo_hora returned NULL for a labor paid entirely via horas_extras — "
        "query must sum horas_trabajadas + horas_extras, not just horas_trabajadas"
    )
    assert isinstance(costo_hora, decimal.Decimal)
    assert costo_hora == round(costo_total / horas_extras)


def test_140_costo_hora_unchanged_for_regular_hours_rows(conn):
    """
    Regression: para labores que ya tenian horas_trabajadas>0 y horas_extras=0,
    el costo_hora debe seguir siendo total_labor / horas_trabajadas (sin cambios
    de comportamiento para el caso normal, ya cubierto antes del fix #140).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                SUM(horas_trabajadas) AS horas_trabajadas,
                SUM(horas_extras)     AS horas_extras,
                SUM(total_labor)      AS costo_total,
                CASE WHEN SUM(horas_trabajadas) + SUM(horas_extras) > 0
                     THEN ROUND((SUM(total_labor)
                          / (SUM(horas_trabajadas) + SUM(horas_extras)))::numeric, 0)
                     ELSE NULL END AS costo_hora
            FROM appsheet.tarjas_reporte
            WHERE contratista = 'HERBI ML SPA'
              AND nombre_campo ILIKE '%iga'
              AND "CC" = '866'
              AND fecha BETWEEN '2026-08-19' AND '2026-08-25'
            GROUP BY tipo_pago, "Nombre Labor", "CC"
            """
        )
        row = cur.fetchone()
    assert row is not None, "No matching rows for the regular-hours regression case"
    horas_trabajadas, horas_extras, costo_total, costo_hora = row
    assert horas_trabajadas > 0
    assert costo_hora == round(costo_total / horas_trabajadas)
