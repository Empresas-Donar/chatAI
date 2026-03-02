# AppSheet → PostgreSQL Generator

Automatic schema and data-load generator from CSV files.

Reads all CSVs in `raw_csv/<app>/`, infers column types, and produces:
- `generated_sql/<app>/01_schema.sql` — `CREATE SCHEMA` + `CREATE TABLE`
- `generated_sql/<app>/02_load_data.sql` — `COPY` statements (server-side)

Optionally loads data directly via psycopg2 (client-side, no server access needed).

---

## Installation

```bash
pip install pandas psycopg2-binary pyyaml python-dotenv
```

Python 3.10+ required.

---

## Project Structure

```
generator/
├── main.py              # CLI entrypoint
├── schema_generator.py  # Reads CSVs, builds CREATE TABLE SQL
├── data_loader.py       # Loads rows into PostgreSQL via psycopg2
├── type_inference.py    # Infers PostgreSQL types from CSV columns
├── config.yaml          # App definitions, DB connection, overrides
├── raw_csv/             # Place CSV exports here (one subfolder per app)
│   └── contratistas_isla_maipo/
│       ├── empresa.csv
│       └── ...
└── generated_sql/       # Output directory (auto-created)
    └── contratistas_isla_maipo/
        ├── 01_schema.sql
        └── 02_load_data.sql
```

---

## Usage

### 1. Place your CSV files

```
raw_csv/
└── <app_name>/
    ├── tabla1.csv
    ├── tabla2.csv
    └── ...
```

### 2. Generate SQL only

```bash
cd generator/
python main.py --app contratistas_isla_maipo
```

Produces `generated_sql/contratistas_isla_maipo/01_schema.sql` and `02_load_data.sql`.

### 3. Generate SQL and load data (client-side)

```bash
python main.py --app contratistas_isla_maipo --load
```

Requires DB credentials in `config.yaml` or environment variables:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=mydb
export DB_USER=myuser
export DB_PASSWORD=secret
```

### 4. Apply the generated SQL manually (server-side COPY)

```bash
psql $DATABASE_URL -f generated_sql/contratistas_isla_maipo/01_schema.sql
psql $DATABASE_URL -f generated_sql/contratistas_isla_maipo/02_load_data.sql
```

> **Note:** `02_load_data.sql` uses `COPY FROM '/path/...'` which requires the
> CSV files to be accessible by the **PostgreSQL server process**.
> Update `csv_server_base_path` in `config.yaml` to match your server's path.
> If your DB is remote, use `--load` (psycopg2 client-side) instead.

---

## Adding a New App

1. Create a folder: `raw_csv/<new_app>/`
2. Copy your CSVs there.
3. Add an entry in `config.yaml`:

```yaml
apps:
  new_app:
    schema: appsheet          # PostgreSQL schema name
    table_overrides: {}       # optional filename → table name mapping
    load_order: []            # optional FK-safe load order
    force_types: {}           # optional column type overrides
```

4. Run:

```bash
python main.py --app new_app
```

---

## Forcing Column Types

If type inference gets a column wrong, override it in `config.yaml`:

```yaml
apps:
  contratistas_isla_maipo:
    force_types:
      "Fecha_Inicio": DATE
      "ID_Trabajador": TEXT
      "%Jornada_Bono": "NUMERIC(12,2)"
```

> Column names must match the CSV header exactly (case-sensitive, accents, special chars).

---

## Type Inference Rules

| Condition | PostgreSQL type |
|---|---|
| > 30% empty values | `TEXT` |
| All values are `true`/`false`/`yes`/`no`/`1`/`0` | `BOOLEAN` |
| All values match `YYYY-MM-DD` | `DATE` |
| All values match `YYYY-MM-DD HH:MM...` | `TIMESTAMP` |
| All values are whole numbers | `INTEGER` |
| All values are decimals | `NUMERIC(12,2)` |
| Mixed or unrecognized | `TEXT` |

---

## Example Generated SQL

**01_schema.sql**
```sql
CREATE SCHEMA IF NOT EXISTS "appsheet";

-- Table: empresa  (source: empresa.csv)
CREATE TABLE IF NOT EXISTS "appsheet"."empresa" (
    "CC" TEXT,
    "Empresa" TEXT
);

-- Table: contratistas  (source: contratistas.csv)
CREATE TABLE IF NOT EXISTS "appsheet"."contratistas" (
    "Id_Supervisor" TEXT,
    "Contratista" TEXT,
    "%Jornada_Bono" NUMERIC(12,2),
    "Bonificación" NUMERIC(12,2)
);
```

**02_load_data.sql**
```sql
COPY "appsheet"."empresa"
FROM '/tmp/raw_csv/empresa.csv'
WITH (FORMAT csv, HEADER true, NULL '');

COPY "appsheet"."contratistas"
FROM '/tmp/raw_csv/contratistas.csv'
WITH (FORMAT csv, HEADER true, NULL '');
```

---

## Key Design Decisions

- **Column names are never modified.** Exact CSV headers go into the SQL with double quotes.
- **No primary keys, no foreign keys** in this phase — it's a 1:1 structural copy.
- **Empty cells → NULL**, never empty strings.
- **`ON CONFLICT DO NOTHING`** in the psycopg2 loader prevents duplicate errors on re-runs.
- **load_order** in config.yaml lets you control FK-safe insertion order without touching code.
