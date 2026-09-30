"""Contractor reports must not include tipo_pago Tractorista.

Those rows belong to the tractorista section (Detalle / General / Resumen
and the tractorista purchase order).
"""
import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import controllers.tarjas_controller as tc  # noqa: E402
import tarjas_empresa as te  # noqa: E402

CONTRATISTA = "AGROSERVICIOS C Y G SPA"
EMPRESA = "ZUÑIGA"
FECHA_INICIO = "2026-09-01"
FECHA_TERMINO = "2026-09-30"


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


def test_not_tractorista_sql_matches_existing_predicate():
    assert te.not_tractorista_sql() == "NOT (LOWER(TRIM(tipo_pago)) = 'tractorista')"
    assert te.not_tractorista_sql("p.tipo_pago") == (
        "NOT (LOWER(TRIM(p.tipo_pago)) = 'tractorista')"
    )


def test_detalle_filters_exclude_tractorista():
    where, _params = tc._build_detalle_filters(FECHA_INICIO, FECHA_TERMINO)
    assert te.not_tractorista_sql() in where


def test_detalle_agroservice_septiembre_sin_tractorista(conn):
    """The week-detail screen for this contractor was showing only Tractorista."""
    where, params = tc._build_detalle_filters(
        FECHA_INICIO,
        FECHA_TERMINO,
        contratista=CONTRATISTA,
        empresa=EMPRESA,
    )
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT tipo_pago, COUNT(*)
            FROM appsheet.tarjas_pagos
            WHERE fecha::date BETWEEN %s AND %s
              AND contratista = %s
              AND nombre_campo = %s
              AND estado = 'Aprobado'
              AND LOWER(TRIM(tipo_pago)) = 'tractorista'
            GROUP BY tipo_pago
            """,
            (FECHA_INICIO, FECHA_TERMINO, CONTRATISTA, EMPRESA),
        )
        leaked_source = cur.fetchall()
        assert leaked_source, "fixture has no tractorista rows to exclude"

        cur.execute(
            f"""
            SELECT DISTINCT tipo_pago
            FROM appsheet.tarjas_pagos
            {where}
            """,
            params,
        )
        tipos = {(r[0] or "").strip().lower() for r in cur.fetchall()}
    assert "tractorista" not in tipos
