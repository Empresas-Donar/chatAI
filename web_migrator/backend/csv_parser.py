"""
csv_parser.py
-------------
Parses uploaded CSV files into structured TableAnalysis objects.
Detects table name from filename, infers column types, and collects warnings.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from type_inference import ColumnInfo, analyze_column, detect_duplicate_ids


@dataclass
class TableAnalysis:
    table_name: str          # Derived from CSV filename (stem)
    filename: str            # Original filename
    row_count: int
    column_count: int
    columns: list[ColumnInfo]
    preview: list[dict]      # First 20 rows as list of dicts
    warnings: list[str]      # Table-level warnings
    file_path: str           # Absolute path to the uploaded CSV


def parse_csv(file_path: Path, app_name: str) -> TableAnalysis:
    """
    Read a CSV file and return a full TableAnalysis.
    Column names are preserved exactly — only leading/trailing whitespace stripped.
    """
    table_name = file_path.stem  # filename without extension

    df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    df.columns = [col.strip() for col in df.columns]

    row_count = len(df)
    column_count = len(df.columns)
    table_warnings = []

    if row_count == 0:
        table_warnings.append("CSV has no data rows")

    # Analyze each column
    columns: list[ColumnInfo] = []
    for col in df.columns:
        col_info = analyze_column(df[col], col)
        columns.append(col_info)

    # Detect duplicate values in the first column (assumed PK candidate)
    if len(df.columns) > 0:
        first_col = df.columns[0]
        dupes = detect_duplicate_ids(df[first_col])
        if dupes:
            sample = dupes[:5]
            table_warnings.append(
                f"Possible duplicate IDs in '{first_col}': "
                + ", ".join(sample)
                + ("..." if len(dupes) > 5 else "")
            )

    # Preview: first 20 rows, replace empty strings with None for display
    preview_df = df.head(20).where(df.head(20) != "", other=None)
    preview = preview_df.to_dict(orient="records")

    return TableAnalysis(
        table_name=table_name,
        filename=file_path.name,
        row_count=row_count,
        column_count=column_count,
        columns=columns,
        preview=preview,
        warnings=table_warnings,
        file_path=str(file_path),
    )
