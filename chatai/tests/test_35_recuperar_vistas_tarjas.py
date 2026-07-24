"""
Regression tests for issue #35: vistas tarjas_reporte y tarjas_reporte_odoo
eliminadas silenciosamente por ALTER TABLE ... ALTER COLUMN TYPE ... CASCADE.

Root cause: commit 3de2bfd hizo ALTER TABLE appsheet.tarjas_pagos ALTER COLUMN
id_labor TYPE TEXT CASCADE. PostgreSQL eliminó automáticamente las dos vistas
dependientes como efecto colateral del CASCADE.

Segundo bug encontrado: la vista 02_views_odoo.sql referenciaba l0.id_labor
pero tarjas_labores no tenía esa columna. Se agregó como columna generada
(GENERATED ALWAYS AS (codigo_labor) STORED) en 06_add_id_labor_to_labores.sql.

Fixes:
1. Re-ejecutar sql/tarjas/01_views_reporte.sql → recrea appsheet.tarjas_reporte
2. Ejecutar sql/tarjas/06_add_id_labor_to_labores.sql → agrega id_labor a tarjas_labores
3. Re-ejecutar sql/tarjas/02_views_odoo.sql → recrea appsheet.tarjas_reporte_odoo
"""

import os

import psycopg2
import pytest


# ---------------------------------------------------------------------------
# DB connection fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_conn():
    """Connect to production DB using env vars or .env defaults."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "34.176.199.22"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "donar_prod"),
        user=os.getenv("DB_USER", "donar"),
        password=os.getenv("DB_PASSWORD", "N7@pX9!K2L#fQ8rM$D5WcE%ZJ^H@A3"),
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Regression tests — issue #35
# ---------------------------------------------------------------------------


class TestIssue35RecuperarVistasTarjas:
    """Regression: both views must exist and return data after the fix."""

    def test_35_recuperar_vistas_tarjas_regression_tarjas_reporte_exists(self, db_conn):
        """tarjas_reporte must exist in the appsheet schema."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'appsheet'
                  AND c.relname = 'tarjas_reporte'
                  AND c.relkind = 'v'
                """
            )
            count = cur.fetchone()[0]
        assert count == 1, "appsheet.tarjas_reporte debe existir como vista"

    def test_35_recuperar_vistas_tarjas_regression_tarjas_reporte_odoo_exists(
        self, db_conn
    ):
        """tarjas_reporte_odoo must exist in the appsheet schema."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'appsheet'
                  AND c.relname = 'tarjas_reporte_odoo'
                  AND c.relkind = 'v'
                """
            )
            count = cur.fetchone()[0]
        assert count == 1, "appsheet.tarjas_reporte_odoo debe existir como vista"

    def test_35_recuperar_vistas_tarjas_regression_tarjas_reporte_returns_rows(
        self, db_conn
    ):
        """tarjas_reporte must return at least one row (view is queryable)."""
        with db_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM appsheet.tarjas_reporte")
            count = cur.fetchone()[0]
        assert count > 0, (
            "appsheet.tarjas_reporte debe devolver filas (hay pagos aprobados)"
        )

    def test_35_recuperar_vistas_tarjas_regression_tarjas_reporte_odoo_returns_rows(
        self, db_conn
    ):
        """tarjas_reporte_odoo must return at least one row (view is queryable)."""
        with db_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM appsheet.tarjas_reporte_odoo")
            count = cur.fetchone()[0]
        assert count > 0, "appsheet.tarjas_reporte_odoo debe devolver filas"

    def test_35_recuperar_vistas_tarjas_regression_id_labor_col_in_tarjas_labores(
        self, db_conn
    ):
        """tarjas_labores must have an id_labor column (generated from codigo_labor)."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'appsheet'
                  AND table_name = 'tarjas_labores'
                  AND column_name = 'id_labor'
                """
            )
            count = cur.fetchone()[0]
        assert count == 1, (
            "appsheet.tarjas_labores debe tener columna id_labor "
            "(usada en el JOIN l0 de tarjas_reporte_odoo)"
        )

    def test_35_recuperar_vistas_tarjas_regression_id_labor_equals_codigo_labor(
        self, db_conn
    ):
        """tarjas_labores.id_labor must equal codigo_labor (generated column invariant)."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM appsheet.tarjas_labores
                WHERE id_labor IS DISTINCT FROM codigo_labor
                """
            )
            count = cur.fetchone()[0]
        assert count == 0, (
            "tarjas_labores.id_labor debe ser igual a codigo_labor en todas las filas"
        )

    def test_35_recuperar_vistas_tarjas_regression_l0_join_resolves(self, db_conn):
        """Rows with id_labor populated in tarjas_pagos must resolve order_line/product_id
        via the l0 direct join in tarjas_reporte_odoo."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM appsheet.tarjas_reporte_odoo
                WHERE "order_line/product_id" IS NOT NULL
                """
            )
            count = cur.fetchone()[0]
        assert count > 0, (
            "Al menos una fila de tarjas_reporte_odoo debe resolver "
            "order_line/product_id via el JOIN l0 (id_labor directo)"
        )

    def test_35_cross_farm_isolation_tarjas_reporte_scoped(self, db_conn):
        """tarjas_reporte must only expose rows whose underlying tarjas_pagos.estado = 'Aprobado'.

        Verifica que no hay ningun contratista+fecha+campo que aparezca en tarjas_reporte
        pero NO tenga filas aprobadas en tarjas_pagos. Es decir, la vista no filtra mal
        y devuelve datos de estados distintos a Aprobado.
        """
        with db_conn.cursor() as cur:
            # All (contratista, nombre_campo, fecha) combinations in tarjas_reporte
            # must have at least one Aprobado row in tarjas_pagos.
            cur.execute(
                """
                SELECT COUNT(*)
                FROM appsheet.tarjas_reporte r
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM appsheet.tarjas_pagos p
                    WHERE p.estado = 'Aprobado'
                      AND p.contratista = r.contratista
                      AND p.nombre_campo = r.nombre_campo
                      AND p.fecha::DATE = r.fecha
                )
                """
            )
            count = cur.fetchone()[0]
        assert count == 0, (
            "tarjas_reporte contiene filas para (contratista, nombre_campo, fecha) "
            "sin ninguna fila Aprobada en tarjas_pagos — filtro WHERE roto."
        )
