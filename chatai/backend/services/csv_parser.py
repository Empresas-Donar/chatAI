"""
services/csv_parser.py
----------------------
Parses uploaded CSV files into TableAnalysis objects.
Business logic only — no HTTP, no DB.
"""

from pathlib import Path

import pandas as pd

from core.type_inference import analyze_column, detect_duplicate_ids
from models.migration_models import TableAnalysis


def parse_csv(file_path: Path, app_name: str) -> TableAnalysis:
    """
    Read a CSV and return a full TableAnalysis.
    Column names preserved exactly — only leading/trailing whitespace stripped.
    """
    df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    df.columns = [col.strip() for col in df.columns]

    warnings = []
    if len(df) == 0:
        warnings.append("CSV has no data rows")

    columns = [analyze_column(df[col], col) for col in df.columns]

    if df.columns.size > 0:
        dupes = detect_duplicate_ids(df[df.columns[0]])
        if dupes:
            sample = ", ".join(dupes[:5]) + ("..." if len(dupes) > 5 else "")
            warnings.append(f"Possible duplicate IDs in '{df.columns[0]}': {sample}")

    preview = df.head(20).where(df.head(20) != "", other=None).to_dict(orient="records")

    return TableAnalysis(
        table_name=file_path.stem,
        filename=file_path.name,
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
        preview=preview,
        warnings=warnings,
        file_path=str(file_path),
    )
