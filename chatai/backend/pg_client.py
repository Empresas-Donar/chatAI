"""
pg_client.py
------------
PostgreSQL query helpers for the chat controller.
Connects using the same DB_* env vars as the rest of the app.
"""

import logging
import os
import decimal
import datetime
import re
import psycopg2
import psycopg2.extras


def _get_conn():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def _serialize(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return str(v)
    if isinstance(v, datetime.timedelta):
        return str(v)
    return v


_WRITE_PATTERN = re.compile(
    r"^\s*(insert|update|delete|drop|truncate|alter|create|grant|revoke|copy|call|do|execute|vacuum|analyze|lock)\b",
    re.IGNORECASE,
)
# Also block CTEs that write: WITH ... INSERT/UPDATE/DELETE
_WRITE_CTE_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke)\b",
    re.IGNORECASE,
)


def run_pg_query(sql: str, max_rows: int = 200) -> list[dict]:
    if _WRITE_PATTERN.match(sql):
        raise ValueError("Solo se permiten consultas SELECT en el chat")
    # Block write operations inside CTEs (WITH ... INSERT/UPDATE/DELETE)
    if _WRITE_CTE_PATTERN.search(sql):
        raise ValueError("Solo se permiten consultas SELECT en el chat")
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchmany(max_rows)
            return [{k: _serialize(v) for k, v in row.items()} for row in rows]
    except psycopg2.Error as e:
        logging.getLogger("pg_client").error("Query error %s: %s", e.pgcode, e.pgerror)
        # Return the SQL error to the model so it can self-correct
        msg = str(e.pgerror or e).strip().split("\n")[0]
        raise ValueError(f"PostgreSQL error {e.pgcode}: {msg}")
    finally:
        conn.close()
