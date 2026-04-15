"""
services/sync_service.py
------------------------
Synchronizes validated CSV data into PostgreSQL.
Business logic only — no HTTP concerns.

- Schema: always "appsheet"
- Each table wrapped in its own transaction
- Supports dry_run and SSE log streaming via queue
"""

import logging
import os
import queue
import threading
from typing import Optional

import pandas as pd
import psycopg

from core.type_inference import _is_empty
from models.migration_models import SyncResult, TableAnalysis, TableResult
from services.schema_builder import (
    FIXED_SCHEMA,
    build_create_schema,
    build_create_table,
    full_table_name,
)

logger = logging.getLogger("services.sync")

# Per-job log queues: job_id → Queue[str | None]  (None = sentinel/done)
_log_queues: dict[str, queue.Queue] = {}
_log_lock = threading.Lock()


def create_log_queue(job_id: str) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    with _log_lock:
        _log_queues[job_id] = q
    return q


def get_log_queue(job_id: str) -> Optional[queue.Queue]:
    with _log_lock:
        return _log_queues.get(job_id)


def remove_log_queue(job_id: str) -> None:
    with _log_lock:
        _log_queues.pop(job_id, None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync(
    app_name: str,
    analyses: list[TableAnalysis],
    dry_run: bool = False,
    job_id: Optional[str] = None,
    stopped: Optional[threading.Event] = None,
) -> SyncResult:
    log_q = get_log_queue(job_id) if job_id else None
    if stopped is None:
        stopped = threading.Event()

    if dry_run:
        return _dry_run(app_name, analyses, log_q)

    result = SyncResult(app_name=app_name, dry_run=False)
    _emit(log_q, f"Connecting to PostgreSQL ({os.environ.get('DB_HOST', '?')})...")

    with psycopg.connect(_dsn(), autocommit=False) as conn:
        _emit(log_q, f'Connected. Creating schema "{FIXED_SCHEMA}"...')
        with conn.transaction():
            conn.execute(build_create_schema())

        for i, analysis in enumerate(analyses, 1):
            if stopped.is_set():
                _emit(log_q, "Sync stopped by user.")
                break
            _emit(log_q, f"--- [{i}/{len(analyses)}] {analysis.table_name} ---")
            result.tables.append(_insert_table(conn, app_name, analysis, log_q, stopped))

    _emit(log_q, f"=== Sync complete. {result.total_inserted} rows inserted. ===")
    if log_q:
        log_q.put(None)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dsn() -> str:
    return (
        f"host={os.environ['DB_HOST']} "
        f"port={os.environ.get('DB_PORT', '5432')} "
        f"dbname={os.environ['DB_NAME']} "
        f"user={os.environ['DB_USER']} "
        f"password={os.environ['DB_PASSWORD']}"
    )


def _emit(log_q: Optional[queue.Queue], msg: str) -> None:
    logger.info(msg)
    if log_q:
        log_q.put(msg)


def _coerce(raw, pg_type: str):
    from core.type_inference import _is_empty
    if _is_empty(raw):
        return None
    v = str(raw).strip()
    if pg_type == "BOOLEAN":
        return v.lower() in {"true", "yes", "1", "si", "sí"}
    if pg_type == "INTEGER":
        try:
            return int(v)
        except ValueError:
            return None
    if pg_type in ("NUMERIC(12,2)", "NUMERIC"):
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None
    return v


def _insert_table(conn, app_name, analysis, log_q, stopped) -> TableResult:
    tname = full_table_name(app_name, analysis.table_name)
    try:
        df = pd.read_csv(analysis.file_path, dtype=str, keep_default_na=False)
        df.columns = [c.strip() for c in df.columns]

        cols_sql = ", ".join(f'"{c.name}"' for c in analysis.columns)
        placeholders = ", ".join(["%s"] * len(analysis.columns))
        insert_sql = f"INSERT INTO {tname} ({cols_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

        _emit(log_q, f"[{analysis.table_name}] Creating table if needed...")
        with conn.transaction():
            cur = conn.cursor()
            cur.execute(build_create_table(app_name, analysis))
            _emit(log_q, f"[{analysis.table_name}] Inserting {len(df)} rows...")
            for i, (_, row) in enumerate(df.iterrows(), 1):
                if stopped.is_set():
                    raise InterruptedError("Cancelled by user")
                values = tuple(_coerce(row.get(c.name, ""), c.pg_type) for c in analysis.columns)
                cur.execute(insert_sql, values)
                if i % 100 == 0 or i == len(df):
                    _emit(log_q, f"[{analysis.table_name}] {i}/{len(df)} rows...")

        _emit(log_q, f"[{analysis.table_name}] ✓ {len(df)} rows done.")
        return TableResult(table_name=analysis.table_name, success=True, rows_inserted=len(df))

    except InterruptedError as exc:
        _emit(log_q, f"[{analysis.table_name}] ✗ Stopped: {exc}")
        return TableResult(table_name=analysis.table_name, success=False, error=str(exc))
    except Exception as exc:
        _emit(log_q, f"[{analysis.table_name}] ✗ Error: {exc}")
        logger.error(f"Failed {tname}: {exc}")
        return TableResult(table_name=analysis.table_name, success=False, error=str(exc))


def _dry_run(app_name, analyses, log_q) -> SyncResult:
    result = SyncResult(app_name=app_name, dry_run=True)
    _emit(log_q, "=== DRY RUN — no DB connection ===")
    for analysis in analyses:
        try:
            df = pd.read_csv(analysis.file_path, dtype=str, keep_default_na=False)
            tname = full_table_name(app_name, analysis.table_name)
            _emit(log_q, f"[{analysis.table_name}] ✓ {len(df)} rows → {tname}")
            result.tables.append(TableResult(table_name=analysis.table_name, success=True, rows_inserted=len(df)))
        except Exception as exc:
            _emit(log_q, f"[{analysis.table_name}] ✗ {exc}")
            result.tables.append(TableResult(table_name=analysis.table_name, success=False, error=str(exc)))
    _emit(log_q, f"=== Dry run complete. {result.total_inserted} rows validated. ===")
    if log_q:
        log_q.put(None)
    return result
