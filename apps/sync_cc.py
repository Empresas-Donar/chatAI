"""
apps/sync_cc.py
---------------
Syncs Odoo analytic accounts (CC_analiticos in BigQuery) into:
  - appsheet.tarjas_cc  : inserts new CC, fixes {"": 100} valor_odoo
  - appsheet.despacho_cc: fixes {"": 100} id_odoo

Run manually:
  python apps/sync_cc.py

Run as cron (example, daily at 6am):
  0 6 * * * cd /path/to/project && python apps/sync_cc.py >> logs/sync_cc.log 2>&1
"""

import datetime
import json
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import psycopg2
from google.cloud import bigquery
from google.oauth2 import service_account

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

BQ_PROJECT = "ace-scarab-484515-v1"
BQ_KEY_PATH = os.environ.get(
    "BQ_KEY_PATH",
    "/Users/bedomax/startups/donar/bigquery-odoo-key.json",
)

COMPANY_TO_CAMPO = {1: 1, 2: 1, 3: 2, 5: 3, 6: 4, 7: 4}
DEFAULT_CAMPO = 1


def _bq_client():
    creds = service_account.Credentials.from_service_account_file(BQ_KEY_PATH)
    return bigquery.Client(project=BQ_PROJECT, credentials=creds)


def _pg_conn():
    # Support DATABASE_URL (used in CI) or individual vars (used locally)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    host = os.environ["DB_HOST"]
    kwargs = dict(
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    if host.startswith("/"):
        return psycopg2.connect(host=host, **kwargs)
    return psycopg2.connect(host=host, port=int(os.environ.get("DB_PORT", 5432)), **kwargs)


def fetch_odoo_cc(bq: bigquery.Client) -> dict[str, dict]:
    """Return {code: {id, nombre, company_id}} for all active Odoo CC with a code."""
    rows = bq.query("""
        SELECT
          id,
          COALESCE(
            JSON_EXTRACT_SCALAR(name, '$.es_CL'),
            JSON_EXTRACT_SCALAR(name, '$.en_US'),
            CAST(id AS STRING)
          ) AS nombre,
          code,
          company_id
        FROM `ace-scarab-484515-v1.odoo_data.CC_analiticos`
        WHERE active = TRUE
          AND code IS NOT NULL
          AND TRIM(code) != ''
    """).result()

    by_code: dict[str, dict] = {}
    for r in rows:
        code = str(r["code"]).strip()
        if code not in by_code:
            by_code[code] = {
                "id": r["id"],
                "nombre": r["nombre"],
                "company_id": r["company_id"],
            }
    log.info(f"Odoo CC activos con código: {len(by_code)}")
    return by_code


def sync_tarjas_cc(odoo: dict[str, dict], conn) -> None:
    active_ids = {str(info["id"]) for info in odoo.values()}

    with conn.cursor() as cur:
        cur.execute("SELECT id_cc::text, valor_odoo FROM appsheet.tarjas_cc")
        existing = {r[0]: r[1] for r in cur.fetchall()}

    to_insert, to_fix = [], []

    for code, info in odoo.items():
        odoo_id = str(info["id"])
        new_json = json.dumps({odoo_id: 100})

        if code not in existing:
            to_insert.append({
                "id_cc": code,
                "cultivo": info["nombre"],
                "id_campo": COMPANY_TO_CAMPO.get(info["company_id"], DEFAULT_CAMPO),
                "valor_odoo": new_json,
            })
        else:
            current = existing[code] or {}
            stored_keys = [k for k in current.keys() if k != ""] if isinstance(current, dict) else []

            if not stored_keys or list(current.keys()) == [""]:
                # Empty or blank-key mapping → fill with active ID
                to_fix.append((new_json, code))
            elif len(stored_keys) == 1 and stored_keys[0] not in active_ids:
                # Simple stale mapping (single archived ID) → replace with current active ID
                log.info(f"tarjas_cc [{code}]: ID {stored_keys[0]} archivado → actualizando a {odoo_id}")
                to_fix.append((new_json, code))
            # Multi-CC distributions are left as-is (require manual review)

    now_iso = datetime.datetime.utcnow().isoformat()
    with conn.cursor() as cur:
        for r in to_insert:
            cur.execute(
                """
                INSERT INTO appsheet.tarjas_cc (id_cc, cultivo, id_campo, valor_odoo)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (id_cc) DO NOTHING
                """,
                (r["id_cc"], r["cultivo"], r["id_campo"], r["valor_odoo"]),
            )
        for new_json, code in to_fix:
            cur.execute(
                "UPDATE appsheet.tarjas_cc SET valor_odoo = %s::jsonb WHERE id_cc = %s",
                (new_json, code),
            )
        # Record sync timestamp so the UI can display it
        cur.execute("""
            CREATE TABLE IF NOT EXISTS appsheet.sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cur.execute("""
            INSERT INTO appsheet.sync_meta (key, value) VALUES ('last_cc_sync', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (now_iso,))

    log.info(f"tarjas_cc → insertados: {len(to_insert)}, corregidos: {len(to_fix)}")


def sync_despacho_cc(odoo: dict[str, dict], conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id_producto, producto, id_odoo FROM appsheet.despacho_cc")
        rows = cur.fetchall()

    to_fix = []
    for id_producto, producto, id_odoo_raw in rows:
        match = re.match(r'^(\S+?)-', producto or "")
        if not match:
            continue
        code = match.group(1).strip()
        if code not in odoo:
            continue

        current = {}
        if id_odoo_raw:
            try:
                current = json.loads(id_odoo_raw.strip().rstrip("\r\n"))
            except json.JSONDecodeError:
                pass

        if isinstance(current, dict) and list(current.keys()) == [""]:
            odoo_id = str(odoo[code]["id"])
            to_fix.append((json.dumps({odoo_id: 100}), id_producto))

    with conn.cursor() as cur:
        for new_json, id_producto in to_fix:
            cur.execute(
                "UPDATE appsheet.despacho_cc SET id_odoo = %s WHERE id_producto = %s",
                (new_json, id_producto),
            )

    log.info(f"despacho_cc → corregidos: {len(to_fix)}")


def run() -> None:
    log.info("=== sync_cc start ===")
    bq = _bq_client()
    odoo = fetch_odoo_cc(bq)

    conn = _pg_conn()
    try:
        sync_tarjas_cc(odoo, conn)
        sync_despacho_cc(odoo, conn)
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("Sync failed — rolled back")
        raise
    finally:
        conn.close()

    log.info("=== sync_cc done ===")


if __name__ == "__main__":
    run()
