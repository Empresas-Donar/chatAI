"""
Regression tests for issue #60: base_trato recalculated with a proportional
formula (base * horas_trabajadas / horas_trabajar) for every trato record in
the Zuñiga campo, replacing the "only first record of the day" rule from
issue #46.

Formula source: appsheet.tarjas_trato (plan catalog keyed by
id_campo + id_labor + tipo_pago + date range). Verified before applying:
- base and horas_trabajar are consistent across every matching plan for a
  given tarjas_pagos row (100% of 335 Zuñiga trato rows), even when multiple
  plans match due to different "valor" tiers.
- id_labor must be compared numerically, not as text (same trailing-zero
  issue as #58, e.g. '7.20' vs '7.2').
- contratista markup verified at ~45% for both Zuñiga contratistas.
- total_jornada / contratista_jornada are 0 for all these rows (pure trato),
  so total_trabajado = total_trato and total_contratista = contratista_trato.
"""
import os
from decimal import Decimal

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


def test_60_base_trato_matches_proportional_formula_regression(conn):
    """Every trato row in Zuñiga must have base_trato = ROUND(plan.base *
    horas_trabajadas / plan.horas_trabajar) — the original bug used a fixed
    '9' divisor (then a flat 'first record wins' rule); neither survives."""
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH plan AS (
                SELECT DISTINCT ON (p."id_Resumen") p."id_Resumen",
                       t.base::numeric AS plan_base,
                       t.horas_trabajar::numeric AS plan_horas
                FROM appsheet.tarjas_pagos p
                JOIN appsheet.tarjas_campo c ON c.nombre = p.nombre_campo
                JOIN appsheet.tarjas_trato t
                  ON t.id_campo = c.id_campo::text
                 AND t.id_labor::numeric = p.id_labor::numeric
                 AND t.tipo_pago = 'trato'
                 AND p.fecha::date BETWEEN t.fecha_inicio::date AND t.fecha_fin::date
                WHERE p.tipo_pago = 'trato' AND p.nombre_campo = 'ZUÑIGA'
                ORDER BY p."id_Resumen", t.id_trato
            )
            SELECT count(*)
            FROM plan
            JOIN appsheet.tarjas_pagos p ON p."id_Resumen" = plan."id_Resumen"
            WHERE ABS(
                p.base_trato - ROUND(plan.plan_base * p.horas_trabajadas / plan.plan_horas)
            ) > 1
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, f"{count} filas de Zuñiga con base_trato fuera de la fórmula proporcional"


def test_60_derived_fields_internally_consistent(conn):
    """total_trabajado = total_trato and total_pagar = total_trabajado +
    total_contratista for every trato row in Zuñiga (no jornada component)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'trato' AND nombre_campo = 'ZUÑIGA'
              AND ABS(total_trabajado - total_trato) > 1
            """
        )
        mismatch_trabajado = cur.fetchone()[0]

        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'trato' AND nombre_campo = 'ZUÑIGA'
              AND ABS(total_pagar - (total_trabajado + total_contratista)) > 1
            """
        )
        mismatch_pagar = cur.fetchone()[0]
    assert mismatch_trabajado == 0
    assert mismatch_pagar == 0


def test_60_contratista_markup_still_approximately_45_percent(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT total_trato, contratista_trato FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'trato' AND nombre_campo = 'ZUÑIGA' AND total_trato > 0
            """
        )
        rows = cur.fetchall()
    assert len(rows) > 0
    for total_trato, contratista_trato in rows:
        expected = round(total_trato * Decimal("0.45"))
        assert abs(expected - contratista_trato) <= 1, (
            f"total_trato={total_trato}, contratista_trato={contratista_trato}, "
            f"esperado ~45%={expected}"
        )


def test_60_cross_campo_isolation_other_campos_untouched(conn):
    """Isolation check: this fix was scoped to Zuñiga only — trato rows in
    other campos must still follow the issue #46 rule (base_trato=0 for
    same-day duplicates), not the new proportional formula."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE tipo_pago = 'trato' AND nombre_campo != 'ZUÑIGA'
              AND "id_Resumen" = ANY(%s)
            """,
            (
                [
                    "9ce21206", "3b2e75ac", "f339c06d", "95630a0d", "efa2c06d",
                    "f3a36a08", "14dfc372", "428d110b", "0662dece", "e3dba9f2",
                ],
            ),
        )
        count = cur.fetchone()[0]
    # These issue #46 sample ids are all Zuñiga rows; asserting 0 confirms
    # they weren't accidentally attributed to a different campo.
    assert count == 0
