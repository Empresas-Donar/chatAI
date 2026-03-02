"""
type_inference.py
-----------------
Infers PostgreSQL column types from a pandas Series of raw string values.

Rules (applied in order):
  1. If > 30% of non-header values are empty  → TEXT
  2. If all non-empty values are boolean-like  → BOOLEAN
  3. If all non-empty values are ISO dates     → DATE
  4. If all non-empty values are datetimes     → TIMESTAMP
  5. If all non-empty values are integers      → INTEGER
  6. If all non-empty values are decimals      → NUMERIC(12,2)
  7. Otherwise                                 → TEXT
"""

import re
from typing import Optional

import pandas as pd

# Patterns
_RE_INTEGER  = re.compile(r"^-?\d+$")
_RE_DECIMAL  = re.compile(r"^-?\d+[.,]\d+$")
_RE_DATE     = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")

_BOOLEAN_VALUES = {"true", "false", "yes", "no", "1", "0", "si", "sí"}

EMPTY_THRESHOLD = 0.30  # If more than 30% empty → TEXT


def _is_empty(value: str) -> bool:
    return value is None or str(value).strip() == "" or str(value).strip().lower() == "nan"


def _match_all(series: pd.Series, pattern: re.Pattern) -> bool:
    """Return True if every non-empty value matches the given regex."""
    non_empty = [str(v).strip() for v in series if not _is_empty(v)]
    if not non_empty:
        return False
    return all(pattern.match(v) for v in non_empty)


def _all_boolean(series: pd.Series) -> bool:
    non_empty = [str(v).strip().lower() for v in series if not _is_empty(v)]
    if not non_empty:
        return False
    return all(v in _BOOLEAN_VALUES for v in non_empty)


def infer_pg_type(series: pd.Series) -> str:
    """
    Given a pandas Series of raw string values (one CSV column),
    return the best-fit PostgreSQL type string.
    """
    total = len(series)
    if total == 0:
        return "TEXT"

    empty_count = sum(1 for v in series if _is_empty(v))
    empty_ratio = empty_count / total

    # Rule 1: too many empties → TEXT
    if empty_ratio > EMPTY_THRESHOLD:
        return "TEXT"

    # Rule 2: boolean
    if _all_boolean(series):
        return "BOOLEAN"

    # Rule 3: ISO date
    if _match_all(series, _RE_DATE):
        return "DATE"

    # Rule 4: datetime
    if _match_all(series, _RE_DATETIME):
        return "TIMESTAMP"

    # Rule 5: integer
    if _match_all(series, _RE_INTEGER):
        return "INTEGER"

    # Rule 6: decimal
    if _match_all(series, _RE_DECIMAL):
        return "NUMERIC(12,2)"

    # Rule 7: fallback
    return "TEXT"
