"""
services/schema_builder.py
--------------------------
Builds PostgreSQL DDL from TableAnalysis objects.
Business logic only — no HTTP, no DB connections.

Convention:
  schema  = "appsheet"
  table   = appsheet.<app_name>_<csv_stem>
"""

import re
from models.migration_models import TableAnalysis

FIXED_SCHEMA = "appsheet"

# Only allow safe identifier characters: letters, digits, underscore, hyphen
_SAFE_IDENTIFIER = re.compile(r'^[a-zA-Z0-9_\-]+$')


def _validate_identifier(value: str, label: str) -> str:
    """Raise ValueError if value contains unsafe characters for a SQL identifier."""
    if not value or not _SAFE_IDENTIFIER.match(value):
        raise ValueError(
            f"Invalid {label} '{value}': only letters, digits, underscores and hyphens allowed"
        )
    return value


def full_table_name(app_name: str, table_stem: str) -> str:
    _validate_identifier(app_name, "app_name")
    _validate_identifier(table_stem, "table_name")
    return f'"{FIXED_SCHEMA}"."{app_name}_{table_stem}"'


def build_create_schema() -> str:
    return f'CREATE SCHEMA IF NOT EXISTS "{FIXED_SCHEMA}";'


def build_create_table(app_name: str, analysis: TableAnalysis) -> str:
    cols = ",\n".join(f'    "{c.name}" {c.pg_type}' for c in analysis.columns)
    return (
        f"CREATE TABLE IF NOT EXISTS {full_table_name(app_name, analysis.table_name)} (\n"
        f"{cols}\n"
        f");"
    )


def build_full_schema_sql(app_name: str, analyses: list[TableAnalysis]) -> str:
    parts = [
        f"-- Auto-generated schema for app: {app_name}",
        f"-- Schema: {FIXED_SCHEMA}", "",
        build_create_schema(), "",
    ]
    for a in analyses:
        parts += [
            f"-- Table: {full_table_name(app_name, a.table_name)}  (source: {a.filename})",
            build_create_table(app_name, a), "",
        ]
    return "\n".join(parts)
