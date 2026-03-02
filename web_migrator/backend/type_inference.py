"""
type_inference.py
-----------------
Infers PostgreSQL column types from pandas Series of raw string values.
Also detects data quality issues: empty columns, duplicate IDs, type mix.

Rules (applied in order):
  1. > 30% empty              → TEXT
  2. All boolean-like         → BOOLEAN
  3. All ISO dates            → DATE
  4. All datetimes            → TIMESTAMP
  5. All integers             → INTEGER
  6. All decimals             → NUMERIC(12,2)
  7. Otherwise                → TEXT
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

_RE_INTEGER  = re.compile(r"^-?\d+$")
_RE_DECIMAL  = re.compile(r"^-?\d+[.,]\d+$")
_RE_DATE     = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")

_BOOLEAN_VALUES = {"true", "false", "yes", "no", "1", "0", "si", "sí"}

EMPTY_THRESHOLD = 0.30


@dataclass
class ColumnInfo:
    name: str
    pg_type: str
    empty_count: int
    total_count: int
    warnings: list[str] = field(default_factory=list)

    @property
    def empty_ratio(self) -> float:
        return self.empty_count / self.total_count if self.total_count else 0


def _is_empty(value) -> bool:
    return value is None or str(value).strip() in ("", "nan", "NaN", "None")


def _non_empty(series: pd.Series) -> list[str]:
    return [str(v).strip() for v in series if not _is_empty(v)]


def _match_all(values: list[str], pattern: re.Pattern) -> bool:
    return bool(values) and all(pattern.match(v) for v in values)


def _all_boolean(values: list[str]) -> bool:
    return bool(values) and all(v.lower() in _BOOLEAN_VALUES for v in values)


def infer_pg_type(series: pd.Series) -> str:
    total = len(series)
    if total == 0:
        return "TEXT"

    empty_count = sum(1 for v in series if _is_empty(v))
    if empty_count / total > EMPTY_THRESHOLD:
        return "TEXT"

    values = _non_empty(series)
    if not values:
        return "TEXT"

    if _all_boolean(values):
        return "BOOLEAN"
    if _match_all(values, _RE_DATE):
        return "DATE"
    if _match_all(values, _RE_DATETIME):
        return "TIMESTAMP"
    if _match_all(values, _RE_INTEGER):
        return "INTEGER"
    if _match_all(values, _RE_DECIMAL):
        return "NUMERIC(12,2)"
    return "TEXT"


def analyze_column(series: pd.Series, col_name: str) -> ColumnInfo:
    total = len(series)
    empty_count = sum(1 for v in series if _is_empty(v))
    pg_type = infer_pg_type(series)
    warnings = []

    if empty_count == total:
        warnings.append("Column is completely empty")
    elif empty_count / total > EMPTY_THRESHOLD:
        warnings.append(f"{empty_count}/{total} values are empty ({empty_count/total:.0%})")

    # Detect type inconsistency: some look like numbers, some don't
    values = _non_empty(series)
    if pg_type == "TEXT" and values:
        numeric_count = sum(
            1 for v in values
            if _RE_INTEGER.match(v) or _RE_DECIMAL.match(v)
        )
        if 0 < numeric_count < len(values):
            warnings.append(
                f"Mixed types: {numeric_count} numeric-looking values among TEXT"
            )

    return ColumnInfo(
        name=col_name,
        pg_type=pg_type,
        empty_count=empty_count,
        total_count=total,
        warnings=warnings,
    )


def detect_duplicate_ids(series: pd.Series) -> list[str]:
    """Return list of values that appear more than once (potential duplicate PKs)."""
    non_empty = [str(v).strip() for v in series if not _is_empty(v)]
    seen = {}
    for v in non_empty:
        seen[v] = seen.get(v, 0) + 1
    return [v for v, count in seen.items() if count > 1]
