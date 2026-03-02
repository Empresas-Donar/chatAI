"""
schema_builder.py
-----------------
Builds PostgreSQL DDL statements from TableAnalysis objects.

Rules:
  - Schema is always "appsheet" (fixed, per project convention)
  - Table name = "<app_name>_<csv_stem>"  e.g. appsheet.contratistas_isla_maipo_empresa
  - All column names wrapped in double quotes
  - No primary keys, no foreign keys, no constraints in this phase
"""

FIXED_SCHEMA = "appsheet"

from csv_parser import TableAnalysis


def full_table_name(app_name: str, table_stem: str) -> str:
    """Returns the fully-qualified table name: "appsheet"."app_name_table" """
    return f'"{FIXED_SCHEMA}"."{app_name}_{table_stem}"'


def build_create_schema() -> str:
    return f'CREATE SCHEMA IF NOT EXISTS "{FIXED_SCHEMA}";'


def build_create_table(app_name: str, analysis: TableAnalysis) -> str:
    """
    Generate CREATE TABLE IF NOT EXISTS statement for a single CSV.
    Table name pattern: appsheet.<app_name>_<table_stem>
    """
    lines = []
    for col in analysis.columns:
        lines.append(f'    "{col.name}" {col.pg_type}')

    columns_sql = ",\n".join(lines)
    tname = full_table_name(app_name, analysis.table_name)
    return (
        f"CREATE TABLE IF NOT EXISTS {tname} (\n"
        f"{columns_sql}\n"
        f");"
    )


def build_full_schema_sql(app_name: str, analyses: list[TableAnalysis]) -> str:
    parts = [
        f"-- Auto-generated schema for app: {app_name}",
        f"-- Schema: {FIXED_SCHEMA}",
        "",
        build_create_schema(),
        "",
    ]
    for analysis in analyses:
        tname = full_table_name(app_name, analysis.table_name)
        parts.append(f"-- Table: {tname}  (source: {analysis.filename})")
        parts.append(build_create_table(app_name, analysis))
        parts.append("")

    return "\n".join(parts)
