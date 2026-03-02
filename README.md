# AppSheet → PostgreSQL Migration Admin

Internal admin tool for migrating AppSheet applications to PostgreSQL.

The workflow is: export CSVs from AppSheet → upload to the web tool → validate schema and data → sync to PostgreSQL → reconnect AppSheet to the new database.

---

## How it works

```
AppSheet (Google Sheets backend)
        │
        │  Export CSVs
        ▼
Web Migrator  (http://localhost:8000)
        │
        │  1. Upload CSVs + set app name
        │  2. Auto-infer column types
        │  3. Preview & validate
        │  4. Dry run (optional)
        │  5. Confirm & Sync
        ▼
PostgreSQL  →  schema: appsheet
                tables: appsheet.<app_name>_<table>
        │
        │  Connect AppSheet → PostgreSQL
        │  Run "Regenerate Structure"
        ▼
AppSheet now reads from PostgreSQL
```

---

## Registered apps

| App name | Status |
|---|---|
| `contratistas_isla_maipo` | Migrated |
| `medicion_pozos` | Pending |

Table naming convention: `appsheet.<app_name>_<table_name>`

---

## Quick start

### 1. Install dependencies

```bash
cd web_migrator/
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp web_migrator/.env.example web_migrator/.env
# Edit .env with real values — never commit this file
```

| Variable | Description |
|---|---|
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port (default `5432`) |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |

### 3. Start the server

```bash
cd web_migrator/
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

To stop: `Ctrl+C`. If the port is busy: `lsof -ti :8000 | xargs kill -9`

---

## Migrating a new app

### Step 1 — Export CSVs from AppSheet

Export each table as CSV. Keep the original filenames — the filename becomes the table name.

> Before writing any SQL or running any migration, take screenshots of each table's column definitions in AppSheet. Column names in AppSheet are the source of truth.

### Step 2 — Upload & validate

1. Open [http://localhost:8000](http://localhost:8000)
2. Enter the **app name** (e.g. `medicion_pozos`) — this becomes the table prefix
3. Select all CSV files for the app
4. Click **Upload & Analyse**

The tool will:
- Infer a PostgreSQL type for every column
- Flag columns with high empty rates, duplicate IDs, or mixed types
- Show a preview of the first 20 rows per table

### Step 3 — Dry run

Click **Dry Run** to validate the full sync path without writing anything to the database. Confirms CSVs are readable and row counts look correct.

### Step 4 — Sync

Click **Confirm & Sync**. The tool will:
- Create schema `appsheet` if it does not exist
- Create each table with inferred types (`CREATE TABLE IF NOT EXISTS`)
- Insert rows with `ON CONFLICT DO NOTHING` — safe to re-run
- Stream real-time logs to the browser
- Roll back only the failing table on error — other tables are unaffected

### Step 5 — Connect AppSheet to PostgreSQL

1. In AppSheet go to **Data → Add a data source → Cloud Database**
2. Enter the PostgreSQL connection details
3. Click **Regenerate Structure** so AppSheet re-reads the column types
4. Test all views and actions in **Preview** mode before publishing

---

## Column name rules

AppSheet is case-sensitive. Column names must match the source exactly — no exceptions.

| Rule | Example |
|---|---|
| Never rename columns | `Id_Supervisor` stays `Id_Supervisor` |
| Preserve accents | `Bonificación` stays `Bonificación` |
| Preserve `%` prefix | `%Jornada_Bono` stays `%Jornada_Bono` |
| Preserve spaces | `Centro de Costo` stays `Centro de Costo` |
| Always double-quote in SQL | `"Bonificación"`, `"%Jornada_Bono"` |

**Columns to never migrate:**

| Column | Reason |
|---|---|
| `_RowNumber` | Virtual Google Sheets column — does not exist in PostgreSQL |
| `Related_*` | AppSheet generates these reverse-ref columns automatically |

---

## Type inference

| Condition | PostgreSQL type |
|---|---|
| > 30% empty values | `TEXT` |
| All `true/false/yes/no/si/sí/1/0` | `BOOLEAN` |
| All match `YYYY-MM-DD` | `DATE` |
| All match `YYYY-MM-DD HH:MM...` | `TIMESTAMP` |
| All whole numbers | `INTEGER` |
| All decimals | `NUMERIC(12,2)` |
| Mixed or unrecognized | `TEXT` |

Primary keys are always `TEXT NOT NULL PRIMARY KEY` — AppSheet generates string IDs.

---

## Project structure

```
Appsheet_migration/
├── web_migrator/                   # Main web tool (FastAPI)
│   ├── backend/
│   │   ├── main.py                 # FastAPI routes + SSE streaming
│   │   ├── csv_parser.py           # CSV → TableAnalysis + preview
│   │   ├── type_inference.py       # Column type inference + warnings
│   │   ├── schema_builder.py       # DDL generation (CREATE SCHEMA/TABLE)
│   │   └── sync_service.py         # PostgreSQL sync, transactions, dry run
│   ├── frontend/
│   │   ├── templates/index.html    # Single-page UI (EN/ES)
│   │   └── static/
│   │       ├── app.js              # UI logic + SSE client
│   │       ├── i18n.js             # EN/ES translations
│   │       └── styles.css
│   ├── uploads/                    # Temp CSV storage (auto-cleaned after sync)
│   ├── .env                        # ⚠ Never commit — contains DB credentials
│   ├── .env.example                # Safe template to commit and share
│   └── requirements.txt
│
├── apps/                           # Legacy per-app Python scripts
├── sql/                            # SQL schema definitions per app
├── data/                           # Raw and processed CSV files per app
├── core/                           # Shared utilities (db, cleaners, loader)
└── logs/                           # Migration output logs
```

---

## Security

- **Never commit `.env`** — it contains database credentials. It is listed in `.gitignore`.
- Use `.env.example` as the safe template to share with the team.
- The web tool is for local use only — do not expose port `8000` to the internet.
- The database user only needs `INSERT` and `CREATE TABLE` on the `appsheet` schema.
- Uploaded CSVs are stored temporarily in `uploads/` and deleted automatically after a successful sync.

---

## Troubleshooting

**`uvicorn: command not found`**
```bash
source web_migrator/.venv/bin/activate
```

**Port already in use**
```bash
lsof -ti :8000 | xargs kill -9
```

**Session expired after server restart**
The tool auto-recovers sessions from disk. If it still fails, re-upload the CSVs — the session is rebuilt in seconds.

**`role "your_user" does not exist`**
Your shell environment has variables that are overriding `.env`. The tool uses `override=True` in `load_dotenv` to prevent this. If the issue persists, check for conflicting exports (`DB_USER`, `DB_HOST`) in your shell profile (`.zshrc`, `.bashrc`).

**AppSheet does not recognize a column type after connecting**
The column was likely inferred as `TEXT` instead of the correct type. Check the validation step — the tool shows inferred types before syncing. Correct the source CSV and re-run.
