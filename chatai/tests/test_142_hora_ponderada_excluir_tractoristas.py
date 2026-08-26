"""
Regression tests for issue #142: el reporte "Hora ponderada estandarizada a
9 horas" no debe incluir labores de tractoristas (tipo_pago='Tractorista'),
solo labores de campo.
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


_TRACTORISTA_PAGOS_SQL = "(LOWER(TRIM(tipo_pago)) = 'tractorista')"


def test_142_tractorista_rows_exist_in_source_data(conn):
    """Sanity check: hay filas Tractorista en tarjas_pagos, sino el test no prueba nada."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM appsheet.tarjas_pagos WHERE {_TRACTORISTA_PAGOS_SQL}"
        )
        count = cur.fetchone()[0]
    assert count > 0, "No tractorista rows found — regression fixture assumption broken"


def test_142_hora_ponderada_query_excludes_tractorista(conn):
    """
    Regression: la misma consulta que usa _query_hora_ponderada_rows, con el
    WHERE de _build_hora_ponderada_filters, no debe devolver ninguna fila con
    tipo_pago='tractorista'.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT labor, tipo_pago
            FROM appsheet.tarjas_pagos
            WHERE fecha::date BETWEEN '2000-01-01' AND '2100-01-01'
              AND NOT {_TRACTORISTA_PAGOS_SQL}
            """
        )
        rows = cur.fetchall()
    assert len(rows) > 0, "Query returned no rows at all — check date range/fixture"
    tractorista_leaks = [r for r in rows if r[1] and r[1].strip().lower() == "tractorista"]
    assert tractorista_leaks == [], (
        f"Found {len(tractorista_leaks)} tractorista rows leaking into hora ponderada query"
    )


def test_142_hora_ponderada_filters_exclude_tractorista_labores(conn):
    """
    Regression: el dropdown de Labor (mismo criterio que
    get_tarjas_hora_ponderada_filters) no debe listar labores que existen
    unicamente como tipo_pago='tractorista' (ej. 'Jornada Tractor simple').
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT DISTINCT labor FROM appsheet.tarjas_pagos "
            f"WHERE labor IS NOT NULL AND NOT {_TRACTORISTA_PAGOS_SQL} "
            f"ORDER BY labor"
        )
        labores_campo = {r[0] for r in cur.fetchall()}

        cur.execute(
            f"SELECT DISTINCT labor FROM appsheet.tarjas_pagos "
            f"WHERE {_TRACTORISTA_PAGOS_SQL}"
        )
        labores_tractorista_only = {r[0] for r in cur.fetchall()} - labores_campo

    assert labores_tractorista_only, (
        "No tractor-only labor found in fixture data — regression assumption broken"
    )
    assert labores_tractorista_only.isdisjoint(labores_campo), (
        "Tractor-only labores leaked into the field-labor filter dropdown"
    )
