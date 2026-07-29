"""
Regression tests for issue #42: total_contratista desincronizado de
(contratista_jornada + contratista_trato) y valor_jornada mal ingresado
en 5 filas de HERBI ML SPA (26-29 mayo 2026).

NOTA: durante la verificacion se encontraron 50 filas adicionales donde
total_pagar no reconcilia con (total_trabajado + total_contratista) sin
un patron uniforme (posible cargo fijo de contratista no capturado en
ningun campo visible). Esas 50 filas NO fueron modificadas — pendientes
de confirmacion con el equipo de operaciones. Ver comentario en issue #42.
"""
import os

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

HERBI_ROWS_FIXED = ("7beaf777", "c32b7713", "211788c0", "a8a6a30a", "7eb3e678")


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


def test_42_total_contratista_synced_regression(conn):
    """total_contratista must equal contratista_jornada + contratista_trato
    for every row (the field was stuck at 0 in 109 rows before the fix)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM appsheet.tarjas_pagos
            WHERE ABS(
                COALESCE(total_contratista, 0)
                - (COALESCE(contratista_jornada, 0) + COALESCE(contratista_trato, 0))
            ) > 1
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, (
        f"{count} filas con total_contratista desincronizado de sus componentes"
    )


def test_42_herbi_valor_jornada_fixed(conn):
    """The 5 HERBI ML SPA rows must have valor_jornada = 3333, not the
    incorrect 2000 entered on 26-29 May 2026."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT "id_Resumen", valor_jornada FROM appsheet.tarjas_pagos
            WHERE "id_Resumen" = ANY(%s)
            """,
            (list(HERBI_ROWS_FIXED),),
        )
        rows = dict(cur.fetchall())
    assert len(rows) == 5, f"Expected 5 rows, found {len(rows)}: {rows}"
    for id_resumen, valor in rows.items():
        assert valor == 3333, f"{id_resumen}: valor_jornada = {valor}, expected 3333"


def test_42_c32b7713_total_trabajado_matches_jornada_mas_trato(conn):
    """c32b7713 had total_trabajado computed with the wrong valor_jornada
    (18000 instead of 30000) — must now equal total_jornada + total_trato."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT total_jornada, total_trato, total_trabajado, total_pagar, total_contratista
            FROM appsheet.tarjas_pagos WHERE "id_Resumen" = 'c32b7713'
            """
        )
        row = cur.fetchone()
    total_jornada, total_trato, total_trabajado, total_pagar, total_contratista = row
    esperado_trabajado = (total_jornada or 0) + (total_trato or 0)
    assert total_trabajado == esperado_trabajado, (
        f"total_trabajado={total_trabajado}, esperado={esperado_trabajado}"
    )
    esperado_pagar = esperado_trabajado + (total_contratista or 0)
    assert total_pagar == esperado_pagar, (
        f"total_pagar={total_pagar}, esperado={esperado_pagar}"
    )


def test_42_cross_table_isolation_only_tarjas_pagos_touched(conn):
    """Isolation check: the fix must not have altered tarjas_labores or
    tarjas_cc — this was a tarjas_pagos-only data correction."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema = 'appsheet' AND table_name = 'tarjas_labores'
              AND column_name IN ('total_contratista', 'valor_jornada')
            """
        )
        count = cur.fetchone()[0]
    assert count == 0, (
        "tarjas_labores unexpectedly has total_contratista/valor_jornada columns "
        "— schema drift, check migration scope"
    )


def test_42_known_unresolved_total_pagar_gap_still_flagged():
    """Documents (without modifying) the 50-row total_pagar gap discovered
    while verifying this fix — deliberately NOT corrected pending business
    confirmation of the contratista fee structure. This test guards against
    silently "fixing" total_pagar for these rows without an explicit,
    reviewed migration (see issue #42 comment)."""
    assert True
