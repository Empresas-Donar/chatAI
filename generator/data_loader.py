"""
data_loader.py
--------------
Loads CSV data into PostgreSQL using psycopg2 row-by-row inserts (as an
alternative to the COPY-based 02_load_data.sql).

Why use this instead of COPY?
  - COPY requires the CSV to be accessible by the PostgreSQL server process.
  - data_loader.py runs on the client machine and streams rows over the
    existing psycopg2 connection, so it works with remote databases.
  - Applies NULL coercion: empty strings become NULL.
  - Applies type coercion based on the inferred column types.

Usage (from CLI via main.py):
    python main.py --app contratistas_isla_maipo --load

Or import and call directly:
    from data_loader import run
    run("contratistas_isla_maipo")
"""

import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2
import yaml

from type_inference import infer_pg_type, _is_empty


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_db_connection(config: dict):
    """
    Build a psycopg2 connection from config.yaml → database section,
    with fallback to environment variables.
    """
    db = config.get("database", {})
    return psycopg2.connect(
        host=db.get("host") or os.environ["DB_HOST"],
        port=db.get("port") or os.environ.get("DB_PORT", 5432),
        dbname=db.get("dbname") or os.environ["DB_NAME"],
        user=db.get("user") or os.environ["DB_USER"],
        password=db.get("password") or os.environ["DB_PASSWORD"],
    )


def get_table_name(csv_filename: str, config: dict, app_name: str) -> str:
    stem = Path(csv_filename).stem
    overrides = (
        config.get("apps", {})
              .get(app_name, {})
              .get("table_overrides", {})
    )
    return overrides.get(stem, stem)


def coerce_value(raw: str, pg_type: str):
    """
    Convert a raw string cell to a Python value appropriate for the column type.
    Empty strings always become None (NULL in PostgreSQL).
    """
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
        # Handle comma as decimal separator
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None

    # DATE, TIMESTAMP, TEXT — pass as string; PostgreSQL will cast
    return v


def load_csv_to_db(
    app_name: str,
    csv_path: Path,
    schema: str,
    table: str,
    conn,
    config: dict,
) -> int:
    """
    Load a single CSV file into the given schema.table.
    Returns the number of rows inserted/upserted.
    """
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df.columns = [col.strip() for col in df.columns]

    if df.empty:
        print(f"  [SKIP] {csv_path.name} — no rows")
        return 0

    # Infer types once per column
    col_types = {col: infer_pg_type(df[col]) for col in df.columns}

    # Build INSERT statement with double-quoted column names
    quoted_cols = ", ".join(f'"{c}"' for c in df.columns)
    placeholders = ", ".join(["%s"] * len(df.columns))
    insert_sql = (
        f'INSERT INTO "{schema}"."{table}" ({quoted_cols})\n'
        f"VALUES ({placeholders})\n"
        f"ON CONFLICT DO NOTHING;"
    )

    inserted = 0
    with conn.cursor() as cur:
        for _, row in df.iterrows():
            values = tuple(
                coerce_value(row[col], col_types[col]) for col in df.columns
            )
            cur.execute(insert_sql, values)
            inserted += 1

    conn.commit()
    return inserted


def run(app_name: str, config_path: str = "config.yaml") -> None:
    """
    Load all CSVs for the given app into PostgreSQL.
    """
    config = load_config(config_path)

    base_dir = Path(__file__).parent
    csv_dir = base_dir / "raw_csv" / app_name

    if not csv_dir.exists():
        raise FileNotFoundError(f"CSV directory not found: {csv_dir}")

    schema = (
        config.get("apps", {})
              .get(app_name, {})
              .get("schema", app_name)
    )

    # Respect load_order from config if defined, otherwise sort alphabetically
    load_order = (
        config.get("apps", {})
              .get(app_name, {})
              .get("load_order", [])
    )

    csv_files = list(csv_dir.glob("*.csv"))
    if not csv_files:
        print(f"[data_loader] No CSV files found in {csv_dir}")
        return

    # Sort by load_order (unordered files go to the end)
    def sort_key(p: Path) -> tuple:
        stem = p.stem
        try:
            return (load_order.index(stem), stem)
        except ValueError:
            return (len(load_order), stem)

    csv_files_sorted = sorted(csv_files, key=sort_key)

    print(f"[data_loader] App:    {app_name}")
    print(f"[data_loader] Schema: {schema}")
    print(f"[data_loader] Connecting to database...")
    conn = get_db_connection(config)

    try:
        total_files = len(csv_files_sorted)
        for i, csv_path in enumerate(csv_files_sorted, 1):
            table = get_table_name(csv_path.name, config, app_name)
            print(f"  [{i}/{total_files}] Loading {csv_path.name} → {schema}.{table} ...", end=" ")
            count = load_csv_to_db(app_name, csv_path, schema, table, conn, config)
            print(f"{count} rows")
    finally:
        conn.close()

    print()
    print("[data_loader] Done.")
