# AppSheet → PostgreSQL Web Migrator

Internal web tool for migrating multiple CSV exports from AppSheet to PostgreSQL.

---

## Features

- Upload multiple CSVs in one go
- Automatic type inference per column (INTEGER, NUMERIC, DATE, TIMESTAMP, BOOLEAN, TEXT)
- Warnings for empty columns, duplicate IDs, and mixed types
- Preview first 20 rows before committing
- Dry run mode — validates without writing to the database
- Per-table transaction rollback on failure
- Column names preserved exactly (double-quoted in SQL)

---

## Installation

```bash
cd web_migrator/
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Environment variables

```bash
cp .env.example .env
# then edit .env with your PostgreSQL credentials
```

| Variable | Description |
|---|---|
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port (default 5432) |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |

---

## Running

```bash
cd web_migrator/
source .venv/bin/activate
export $(cat .env | xargs)      # load env vars

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## How to use

### Step 1 — Upload
- Enter the **app name** (becomes the PostgreSQL schema, e.g. `contratistas_isla_maipo`)
- Select one or more CSV files
- Click **Upload & Analyse**

### Step 2 — Validation
- Each table shows inferred column types, empty-value counts, and warnings
- Click **Preview first 20 rows** to inspect the data
- Fix source CSVs if needed, then re-upload

### Step 3 — Confirm
- Summary of all tables and row counts
- **Dry Run** — validates the sync path without writing to the database
- **Confirm & Sync** — creates schema + tables and inserts all rows

### Step 4 — Result
- Per-table success/failure status
- Row counts inserted
- Error messages for failed tables (other tables are unaffected)

---

## Project structure

```
web_migrator/
├── backend/
│   ├── main.py            # FastAPI app + routes
│   ├── csv_parser.py      # CSV → TableAnalysis
│   ├── type_inference.py  # Column type inference + warnings
│   ├── schema_builder.py  # DDL generation (CREATE SCHEMA / TABLE)
│   └── sync_service.py    # PostgreSQL sync (psycopg v3, transactions)
├── frontend/
│   ├── templates/
│   │   └── index.html     # Single-page UI (Jinja2)
│   └── static/
│       ├── app.js
│       ├── i18n.js        # EN/ES translations
│       └── styles.css
├── uploads/               # Temp storage for uploaded CSVs (auto-cleaned)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Type inference rules

| Condition | PostgreSQL type |
|---|---|
| > 30% empty | `TEXT` |
| All `true/false/yes/no/1/0` | `BOOLEAN` |
| All match `YYYY-MM-DD` | `DATE` |
| All match `YYYY-MM-DD HH:MM...` | `TIMESTAMP` |
| All whole numbers | `INTEGER` |
| All decimals | `NUMERIC(12,2)` |
| Mixed or unrecognized | `TEXT` |

---

## Example SQL generated

```sql
CREATE SCHEMA IF NOT EXISTS "appsheet";

CREATE TABLE IF NOT EXISTS "appsheet"."contratistas_isla_maipo_empresa" (
    "CC" TEXT,
    "Empresa" TEXT
);

CREATE TABLE IF NOT EXISTS "appsheet"."contratistas_isla_maipo_contratistas" (
    "Id_Supervisor" TEXT,
    "Contratista" TEXT,
    "%Jornada_Bono" NUMERIC(12,2),
    "Bonificación" NUMERIC(12,2),
    "Fecha_Inicio" DATE
);
```

---

## Key design decisions

| Decision | Reason |
|---|---|
| Column names never modified | AppSheet is case-sensitive; any rename breaks the connection |
| Double quotes on all identifiers | Preserves `%`, accents, spaces, mixed case |
| No PKs / FKs in phase 1 | 1:1 structural copy — constraints added manually after validation |
| Per-table transactions | One bad table doesn't roll back the others |
| `ON CONFLICT DO NOTHING` | Safe to re-run; idempotent |
| Dry run mode | Lets you validate the full path without risking data |
| Uploads cleaned up after sync | Avoids accumulating large files on disk |
