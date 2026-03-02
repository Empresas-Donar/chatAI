"""
sync_service.py
---------------
Synchronizes validated CSV data into PostgreSQL.

- Schema is always "appsheet" (fixed)
- Table names: appsheet.<app_name>_<table_stem>
- Each table is wrapped in its own transaction (failure rolls back only that table)
- Supports dry_run (no DB connection at all)
- Emits log lines to a queue for SSE streaming
"""

import logging
import os
import queue
import threading
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import psycopg

from csv_parser import TableAnalysis
from schema_builder import build_create_schema, build_create_table, full_table_name, FIXED_SCHEMA
from type_inference import _is_empty

logger = logging.getLogger("sync_service")

# Per-job log queues: job_id → Queue[str | None]  (None = sentinel/done)
_log_queues: dict[str, queue.Queue] = {}
_log_queues_lock = threading.Lock()


def create_log_queue(job_id: str) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    with _log_queues_lock:
        _log_queues[job_id] = q
    return q


def get_log_queue(job_id: str) -> Optional[queue.Queue]:
    with _log_queues_lock:
        return _log_queues.get(job_id)


def remove_log_queue(job_id: str) -> None:
    with _log_queues_lock:
        _log_queues.pop(job_id, None)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TableResult:
    table_name: str
    success: bool
    rows_inserted: int = 0
    error: Optional[str] = None


@dataclass
class SyncResult:
    app_name: str
    dry_run: bool
    tables: list[TableResult] = field(default_factory=list)

    @property
    def total_inserted(self) -> int:
        return sum(t.rows_inserted for t in self.tables)

    @property
    def failed_tables(self) -> list[TableResult]:
        return [t for t in self.tables if not t.success]

    @property
    def succeeded_tables(self) -> list[TableResult]:
        return [t for t in self.tables if t.success]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_dsn() -> str:
    return (
        f"host={os.environ['DB_HOST']} "
        f"port={os.environ.get('DB_PORT', '5432')} "
        f"dbname={os.environ['DB_NAME']} "
        f"user={os.environ['DB_USER']} "
        f"password={os.environ['DB_PASSWORD']}"
    )


def _emit(log_q: Optional[queue.Queue], msg: str) -> None:
    """Send a log line to the SSE queue and to the Python logger."""
    logger.info(msg)
    if log_q:
        log_q.put(msg)


def _coerce_row(row: dict, columns) -> tuple:
    values = []
    for col in columns:
        raw = row.get(col.name, "")
        if _is_empty(raw):
            values.append(None)
            continue
        v = str(raw).strip()
        if col.pg_type == "BOOLEAN":
            values.append(v.lower() in {"true", "yes", "1", "si", "sí"})
        elif col.pg_type == "INTEGER":
            try:
                values.append(int(v))
            except ValueError:
                values.append(None)
        elif col.pg_type in ("NUMERIC(12,2)", "NUMERIC"):
            try:
                values.append(float(v.replace(",", ".")))
            except ValueError:
                values.append(None)
        else:
            values.append(v)
    return tuple(values)


def _insert_table(
    conn,
    app_name: str,
    analysis: TableAnalysis,
    log_q: Optional[queue.Queue],
    stopped: threading.Event,
) -> TableResult:
    tname = full_table_name(app_name, analysis.table_name)

    try:
        df = pd.read_csv(analysis.file_path, dtype=str, keep_default_na=False)
        df.columns = [col.strip() for col in df.columns]

        quoted_cols = ", ".join(f'"{c.name}"' for c in analysis.columns)
        placeholders = ", ".join(["%s"] * len(analysis.columns))
        insert_sql = (
            f"INSERT INTO {tname} ({quoted_cols}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT DO NOTHING"
        )

        _emit(log_q, f"[{analysis.table_name}] Creating table {tname}...")

        with conn.transaction():
            cur = conn.cursor()
            cur.execute(build_create_table(app_name, analysis))
            _emit(log_q, f"[{analysis.table_name}] Table ready. Inserting {len(df)} rows...")

            for i, (_, row) in enumerate(df.iterrows(), 1):
                if stopped.is_set():
                    raise InterruptedError("Sync cancelled by user")
                values = _coerce_row(dict(row), analysis.columns)
                cur.execute(insert_sql, values)
                if i % 100 == 0 or i == len(df):
                    _emit(log_q, f"[{analysis.table_name}] {i}/{len(df)} rows inserted...")

        _emit(log_q, f"[{analysis.table_name}] ✓ Done — {len(df)} rows.")
        return TableResult(table_name=analysis.table_name, success=True, rows_inserted=len(df))

    except InterruptedError as exc:
        _emit(log_q, f"[{analysis.table_name}] ✗ Stopped: {exc}")
        return TableResult(table_name=analysis.table_name, success=False, error=str(exc))
    except Exception as exc:
        _emit(log_q, f"[{analysis.table_name}] ✗ Error: {exc}")
        logger.error(f"Failed to insert {tname}: {exc}")
        return TableResult(table_name=analysis.table_name, success=False, error=str(exc))


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
    """
    Main sync entry point.
    - dry_run=True  → no DB connection, just validate and count rows
    - job_id        → if provided, log lines are pushed to the SSE queue
    - stopped       → threading.Event; set it to cancel mid-sync
    """
    log_q = get_log_queue(job_id) if job_id else None
    if stopped is None:
        stopped = threading.Event()

    if dry_run:
        return _dry_run(app_name, analyses, log_q)

    result = SyncResult(app_name=app_name, dry_run=False)

    _emit(log_q, f"Connecting to PostgreSQL ({os.environ.get('DB_HOST', '?')})...")
    with psycopg.connect(_get_dsn(), autocommit=False) as conn:
        _emit(log_q, f"Connected. Creating schema \"{FIXED_SCHEMA}\"...")
        with conn.transaction():
            conn.execute(build_create_schema())

        total = len(analyses)
        for i, analysis in enumerate(analyses, 1):
            if stopped.is_set():
                _emit(log_q, "Sync stopped by user.")
                break
            _emit(log_q, f"--- [{i}/{total}] Processing: {analysis.table_name} ---")
            table_result = _insert_table(conn, app_name, analysis, log_q, stopped)
            result.tables.append(table_result)

    _emit(log_q, f"=== Sync complete. {result.total_inserted} total rows inserted. ===")
    if log_q:
        log_q.put(None)  # sentinel: stream finished
    return result


def _dry_run(
    app_name: str,
    analyses: list[TableAnalysis],
    log_q: Optional[queue.Queue],
) -> SyncResult:
    result = SyncResult(app_name=app_name, dry_run=True)
    _emit(log_q, "=== DRY RUN — no database connection will be made ===")

    for analysis in analyses:
        try:
            df = pd.read_csv(analysis.file_path, dtype=str, keep_default_na=False)
            tname = full_table_name(app_name, analysis.table_name)
            _emit(log_q, f"[{analysis.table_name}] ✓ {len(df)} rows — would insert into {tname}")
            result.tables.append(TableResult(
                table_name=analysis.table_name,
                success=True,
                rows_inserted=len(df),
            ))
        except Exception as exc:
            _emit(log_q, f"[{analysis.table_name}] ✗ Error reading CSV: {exc}")
            result.tables.append(TableResult(
                table_name=analysis.table_name,
                success=False,
                error=str(exc),
            ))

    _emit(log_q, f"=== Dry run complete. {result.total_inserted} rows validated. ===")
    if log_q:
        log_q.put(None)  # sentinel
    return result
