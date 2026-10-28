"""Intranet contractor master: additive schema, apps stay unlinked."""

import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def _connect():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=20,
    )


@pytest.fixture
def cur():
    conn = _connect()
    conn.autocommit = False
    cursor = conn.cursor()
    try:
        yield cursor
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def test_link_column_is_nullable_text_without_fk(cur):
    cur.execute("""
        SELECT table_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'appsheet'
          AND column_name = 'id_intranet_contratistas'
          AND table_name IN ('tarjas_contratistas', 'cosecha_zuniga_contratistas')
        ORDER BY table_name
    """)
    assert cur.fetchall() == [
        ("cosecha_zuniga_contratistas", "text", "YES"),
        ("tarjas_contratistas", "text", "YES"),
    ]
    cur.execute("""
        SELECT COUNT(*)
        FROM pg_constraint
        WHERE contype = 'f'
          AND conname IN (
            'tarjas_contratistas_id_intranet_fk',
            'cosecha_zuniga_contratistas_id_intranet_fk'
          )
    """)
    assert cur.fetchone()[0] == 0


def test_known_names_are_linked_and_cuadrillas_column_is_untouched(cur):
    cur.execute("""
        SELECT attnum, attname
        FROM pg_attribute
        WHERE attrelid = 'appsheet.cosecha_zuniga_contratistas'::regclass
          AND attname IN ('cuadrillas', 'id_intranet_contratistas')
          AND NOT attisdropped
        ORDER BY attnum
    """)
    names = [name for _, name in cur.fetchall()]
    assert names.index("cuadrillas") < names.index("id_intranet_contratistas")

    cur.execute("""
        SELECT z.contratistas, c.nombre
        FROM appsheet.cosecha_zuniga_contratistas z
        JOIN intranet.contratistas c ON c.id_intranet = z.id_intranet_contratistas
        ORDER BY z.contratistas
    """)
    linked = dict(cur.fetchall())
    assert linked["PLP"] == "SERVICIOS AGRICOLAS PLP SPA"
    assert linked["GUTIERREZ II"] == "SERVICIOS AGRICOLAS GUTIERREZ II SPA"

    cur.execute("""
        SELECT COUNT(*) FROM appsheet.tarjas_contratistas
        WHERE id_intranet_contratistas IS NULL
    """)
    assert cur.fetchone()[0] == 0


def test_delete_master_nulls_link_and_keeps_the_app_row(cur):
    cur.execute("""
        SELECT id_contratista, contratistas, cuadrillas, id_intranet_contratistas
        FROM appsheet.cosecha_zuniga_contratistas
        WHERE contratistas = 'PLP'
    """)
    local_id, nombre, cuadrillas, link = cur.fetchone()
    assert link

    cur.execute("DELETE FROM intranet.contratistas WHERE id_intranet = %s", (link,))
    cur.execute("""
        SELECT contratistas, cuadrillas, id_intranet_contratistas
        FROM appsheet.cosecha_zuniga_contratistas
        WHERE id_contratista = %s
    """, (local_id,))
    kept = cur.fetchone()
    assert kept == (nombre, cuadrillas, None)
    cur.connection.rollback()
