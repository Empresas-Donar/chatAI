"""
schema_generator.py
-------------------
Reads all CSVs in a /raw_csv folder and generates:
  - 01_schema.sql  → CREATE SCHEMA + CREATE TABLE statements
  - 02_load_data.sql → COPY statements for data loading

Column names are preserved EXACTLY as they appear in the CSV headers.
All names are wrapped in double quotes for PostgreSQL case-sensitivity.
No renaming, no normalization, no snake_case conversion.
"""

import os
import textwrap
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from type_inference import infer_pg_type


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_table_name(csv_filename: str, config: dict, app_name: str) -> str:
    """
    Determine the PostgreSQL table name for a given CSV file.
    Checks config.yaml for a manual override; falls back to the filename stem.
    """
    stem = Path(csv_filename).stem  # e.g. "mis_datos" from "mis_datos.csv"
    overrides = (
        config.get("apps", {})
              .get(app_name, {})
              .get("table_overrides", {})
    )
    return overrides.get(stem, stem)


def read_csv_safe(csv_path: Path) -> pd.DataFrame:
    """
    Read a CSV keeping all values as strings.
    Only strips leading/trailing whitespace from header names.
    """
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df.columns = [col.strip() for col in df.columns]
    return df


def build_create_table(schema: str, table: str, df: pd.DataFrame, force_types: dict = None) -> str:
    """
    Build a CREATE TABLE IF NOT EXISTS statement.
    Every column name is double-quoted; types are inferred automatically.
    force_types: dict of {column_name: pg_type} overrides from config.yaml.
    No primary keys, no foreign keys, no constraints in this phase.
    """
    force_types = force_types or {}
    lines = []
    for col in df.columns:
        pg_type = force_types.get(col) or infer_pg_type(df[col])
        # Double-quote the column name to preserve exact casing and special chars
        lines.append(f'    "{col}" {pg_type}')

    columns_sql = ",\n".join(lines)

    return (
        f'CREATE TABLE IF NOT EXISTS "{schema}"."{table}" (\n'
        f"{columns_sql}\n"
        f");"
    )


def generate_schema_sql(app_name: str, schema: str, csv_dir: Path, config: dict) -> str:
    """
    Generate the full 01_schema.sql content:
      - CREATE SCHEMA
      - One CREATE TABLE per CSV
    """
    parts = [
        f'-- Auto-generated schema for app: {app_name}',
        f'-- Schema: {schema}',
        '',
        f'CREATE SCHEMA IF NOT EXISTS "{schema}";',
        '',
    ]

    force_types = (
        config.get("apps", {})
              .get(app_name, {})
              .get("force_types", {})
    )

    for csv_file in sorted(csv_dir.glob("*.csv")):
        table = get_table_name(csv_file.name, config, app_name)
        df = read_csv_safe(csv_file)

        parts.append(f'-- Table: {table}  (source: {csv_file.name})')
        parts.append(build_create_table(schema, table, df, force_types=force_types))
        parts.append('')

    return "\n".join(parts)


def generate_load_sql(app_name: str, schema: str, csv_dir: Path, config: dict) -> str:
    """
    Generate the full 02_load_data.sql content.
    Uses PostgreSQL COPY for fast bulk loading.

    NOTE: The path in the COPY statement must be an absolute path
    accessible by the PostgreSQL server process.
    Update the base path in config.yaml → csv_server_base_path.
    """
    server_base = config.get("csv_server_base_path", "/tmp/raw_csv")

    parts = [
        f'-- Auto-generated data load for app: {app_name}',
        f'-- Update csv_server_base_path in config.yaml to match your server.',
        '',
    ]

    for csv_file in sorted(csv_dir.glob("*.csv")):
        table = get_table_name(csv_file.name, config, app_name)
        server_path = f"{server_base}/{csv_file.name}"

        parts.append(f'-- Load: {table}  (source: {csv_file.name})')
        parts.append(
            f'COPY "{schema}"."{table}"\n'
            f"FROM '{server_path}'\n"
            f"WITH (FORMAT csv, HEADER true, NULL '');"
        )
        parts.append('')

    return "\n".join(parts)


def run(app_name: str, config_path: str = "config.yaml") -> None:
    """
    Main entry point for schema generation.
    Reads CSVs from raw_csv/<app_name>/ and writes SQL to generated_sql/<app_name>/.
    """
    config = load_config(config_path)

    # Resolve directories relative to this script's location
    base_dir = Path(__file__).parent
    csv_dir = base_dir / "raw_csv" / app_name
    out_dir = base_dir / "generated_sql" / app_name

    if not csv_dir.exists():
        raise FileNotFoundError(
            f"CSV directory not found: {csv_dir}\n"
            f"Create it and place your CSV files there."
        )

    out_dir.mkdir(parents=True, exist_ok=True)

    # The schema name defaults to the app name unless overridden in config
    schema = (
        config.get("apps", {})
              .get(app_name, {})
              .get("schema", app_name)
    )

    print(f"[schema_generator] App:    {app_name}")
    print(f"[schema_generator] Schema: {schema}")
    print(f"[schema_generator] CSVs:   {csv_dir}")
    print(f"[schema_generator] Output: {out_dir}")
    print()

    csv_files = list(csv_dir.glob("*.csv"))
    if not csv_files:
        print(f"[schema_generator] WARNING: No CSV files found in {csv_dir}")
        return

    print(f"[schema_generator] Found {len(csv_files)} CSV file(s):")
    for f in sorted(csv_files):
        print(f"  - {f.name}")
    print()

    # Generate 01_schema.sql
    schema_sql = generate_schema_sql(app_name, schema, csv_dir, config)
    schema_path = out_dir / "01_schema.sql"
    schema_path.write_text(schema_sql, encoding="utf-8")
    print(f"[schema_generator] Written: {schema_path}")

    # Generate 02_load_data.sql
    load_sql = generate_load_sql(app_name, schema, csv_dir, config)
    load_path = out_dir / "02_load_data.sql"
    load_path.write_text(load_sql, encoding="utf-8")
    print(f"[schema_generator] Written: {load_path}")

    print()
    print("[schema_generator] Done.")
