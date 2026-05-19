# AppSheet → PostgreSQL Web Migrator

Internal web tool for migrating CSV exports from AppSheet to PostgreSQL, with an AI chat assistant to query business data.

---

## Chat IA — Cómo funciona

El chat permite hacer preguntas en lenguaje natural sobre los datos del negocio (tarjas, pagos, contratistas, despacho, etc.) sin saber SQL.

### Flujo de una pregunta

```
Tú → Gemini → ¿necesita datos?
                 ├── Sí → genera SQL → PostgreSQL → resultados → Gemini → respuesta
                 └── No → responde directo (Looker Studio, preguntas generales)
```

1. **El usuario escribe una pregunta** en el chat
2. **El backend se la pasa a Gemini 2.5 Pro** junto con un *system prompt* que describe las tablas disponibles (columnas, tipos, relaciones)
3. **Gemini decide si necesita consultar datos** — si sí, llama una herramienta (*function calling*) con el SQL que necesita
4. **El backend ejecuta el SQL** en PostgreSQL (solo lectura — escrituras bloqueadas) y devuelve los resultados a Gemini
5. **Gemini redacta la respuesta** en español, analizando los datos recibidos
6. **El backend inyecta la fuente** automáticamente: `📊 Fuente: tabla · N registros · IDs: ...` para trazabilidad

### Caso especial: reportes Looker Studio

Si la pregunta menciona "looker studio" o pide reportes, Gemini responde **directamente sin consultar la base de datos** — los 38 links de reportes están incluidos en el system prompt.

### Anti-alucinación

- Las reglas de integridad están al inicio del system prompt (mayor peso para el modelo)
- Gemini tiene prohibido inventar datos, estimar, o responder sin fuente
- Si no hay datos suficientes, debe decirlo explícitamente
- El backend agrega el badge de fuente aunque Gemini lo omita

### Tecnologías

| Componente | Tecnología |
|---|---|
| Modelo IA | Gemini 2.5 Pro (Vertex AI) |
| Protocolo | Function calling (agentic loop) |
| Base de datos | PostgreSQL (esquema `appsheet`) |
| Historial | `public.chat_history` por usuario |
| Autenticación | Google OAuth2 restringido a `@empresasdonar.cl` |

---

## Servicios de Google Cloud

### Cloud Run
Ejecuta la aplicación FastAPI en un contenedor Docker. Recibe todas las peticiones HTTP (chat, login, migrador). Escala automáticamente según el tráfico. Configurado con mínimo 1 instancia para que el login OAuth funcione correctamente.

### Cloud Build + Artifact Registry
CI/CD del proyecto. Cloud Build lee `cloudbuild.yaml`, construye la imagen Docker, la sube a Artifact Registry y despliega la nueva versión en Cloud Run con un solo comando: `gcloud builds submit`.

### Cloud SQL (PostgreSQL)
Base de datos principal. Almacena los datos migrados desde AppSheet (esquema `appsheet`) y el historial de chat por usuario (`public.chat_history`). Cloud Run se conecta via Cloud SQL Connector sin exponer la DB a internet.

### Secret Manager
Guarda las credenciales de forma segura:
- `SECRET_KEY` — clave para firmar las cookies de sesión
- `GOOGLE_CLIENT_SECRET` — clave OAuth de Google
- `BIGQUERY_KEY_B64` — credenciales de BigQuery en base64

### Vertex AI
**Vertex AI es el puente entre la aplicación y Gemini.** Sin él, habría que entrar a google.com y preguntar manualmente. Con Vertex AI, la aplicación habla con Gemini por código: le manda la pregunta y recibe la respuesta automáticamente.

Google ofrece dos formas de acceder a Gemini:

| | Vertex AI | Google AI Studio |
|---|---|---|
| Para | Empresas / producción | Desarrollo / pruebas |
| Autenticación | Cuenta GCP (gcloud) | API key |
| Integración | Con el resto de GCP | Independiente |

Como toda la infraestructura ya está en Google Cloud, Vertex AI se autentica con la misma cuenta de GCP sin API keys adicionales.

### Google OAuth2
Autenticación de usuarios restringida a cuentas `@empresasdonar.cl`. No es un servicio separado — usa las APIs de Google Identity directamente.

### Diagrama

```
Usuario
  │
  ▼
Cloud Run (FastAPI)
  ├── Cloud SQL       → datos del negocio + historial chat
  ├── Vertex AI       → Gemini 2.5 Pro (razonamiento + SQL)
  ├── Secret Manager  → credenciales
  └── Google OAuth2   → autenticación @empresasdonar.cl

Cloud Build + Artifact Registry → deploy
```

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
