"""
models/migration_models.py
--------------------------
Data shapes for the CSV migration domain.
These are pure data containers — no business logic, no DB access.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from core.type_inference import ColumnInfo  # noqa: re-exported for consumers


@dataclass
class TableAnalysis:
    table_name: str       # Derived from CSV filename stem
    filename: str         # Original filename
    row_count: int
    column_count: int
    columns: list[ColumnInfo]
    preview: list[dict]   # First 20 rows as list of dicts
    warnings: list[str]   # Table-level warnings
    file_path: str        # Absolute path to the uploaded CSV


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
