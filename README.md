# AppSheet → PostgreSQL Migration Toolkit

Framework de migración para múltiples aplicaciones AppSheet hacia PostgreSQL.

Diseñado para soportar varias apps como:

- contratistas_isla_maipo
- medicion_pozos
- futuras apps agrícolas
- futuras apps operativas

---

## Objetivo

Permitir:

- Migración estructurada desde Google Sheets (AppSheet) a PostgreSQL
- Limpieza automática de datos (moneda, porcentaje, fechas)
- Respeto de claves primarias
- Respeto de relaciones (Ref)
- Soporte multi-app
- Reutilización de código

---

## Estructura del Proyecto

```
appsheet-migration/
│
├── README.md
├── requirements.txt
├── .env
│
├── config/
│   └── settings.py
│
├── sql/
│   ├── contratistas_isla_maipo/
│   │   ├── 01_schema.sql
│   │   └── 02_tables.sql
│   │
│   ├── medicion_pozos/
│   │   ├── 01_schema.sql
│   │   └── 02_tables.sql
│   │
│   └── templates/
│
├── data/
│   ├── contratistas_isla_maipo/
│   │   ├── raw/
│   │   └── processed/
│   │
│   ├── medicion_pozos/
│   │   ├── raw/
│   │   └── processed/
│   │
│   └── ...
│
├── apps/
│   ├── contratistas_isla_maipo/
│   │   ├── load_contratistas.py
│   │   ├── load_trabajadores.py
│   │   ├── load_tratos.py
│   │   ├── load_registro.py
│   │   └── load_all.py
│   │
│   ├── medicion_pozos/
│   │   ├── load_pozos.py
│   │   └── load_all.py
│   │
│   └── ...
│
├── core/
│   ├── db.py
│   ├── cleaners.py
│   ├── loader.py
│   └── utils.py
│
└── logs/
```

---

## Configuración

Crear archivo `.env`:

```env
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=
```

---

## Requisitos

Python 3.10+

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Contenido de `requirements.txt`:

```
psycopg2-binary
pandas
python-dotenv
```

---

## Convención de Base de Datos

Todas las tablas siguen el patrón:

```
appsheet.<nombre_app>_<nombre_tabla>
```

Ejemplo:

```
appsheet.contratistas_isla_maipo_contratistas
appsheet.medicion_pozos_ingresos
```

---

## Flujo de Migración

1. Exportar CSV desde AppSheet.
2. Guardar archivos en `data/<app>/raw/`
3. Ejecutar script de migración.
4. Validar conteos en PostgreSQL.
5. Conectar AppSheet a PostgreSQL.
6. Ejecutar "Regenerate Structure".
7. Probar app en preview.

---

## Limpieza Automática

El sistema normaliza:

| Entrada       | Salida         |
|---------------|----------------|
| `$18.000`     | `18000`        |
| `45,00%`      | `0.45`         |
| Boolean       | `TRUE`/`FALSE` |
| Fechas        | `YYYY-MM-DD`   |
| EnumList      | `TEXT[]`       |

---

## Seguridad

- No subir `.env` al repositorio.
- Usar variables de entorno.
- Usar `ON CONFLICT` para evitar duplicados.
- No almacenar contraseñas en texto plano.

---

## Orden Correcto de Migración

1. empresa
2. labor
3. contratistas
4. trabajadores
5. tratos
6. registro
7. registro_trato
8. resumen
9. pagos
10. usuarios

---

## AppSheet + PostgreSQL Conventions

### Por qué PostgreSQL

Google Sheets tiene un límite de ~400k celdas y alta latencia en lecturas. Con muchos registros la app se vuelve lenta. PostgreSQL maneja millones de filas con índices, y AppSheet hace queries directas en vez de descargar toda la hoja.

### Primary Keys

Siempre `TEXT NOT NULL PRIMARY KEY` — nunca `SERIAL` ni `INTEGER`. AppSheet genera sus propios IDs como strings y el nombre de la columna debe coincidir exactamente con el Row ID configurado en la app.

### Columnas que NO se migran

- `_RowNumber` — columna virtual de Sheets, no existe en PostgreSQL
- `Related_*` — columnas de reverse ref, AppSheet las genera automáticamente
- Columnas virtuales / fórmulas de AppSheet

### Mapeo de tipos

| AppSheet      | PostgreSQL    |
|---------------|---------------|
| Text          | `TEXT`        |
| Number / Decimal / Price | `NUMERIC` |
| Date          | `DATE`        |
| DateTime      | `TIMESTAMP`   |
| Yes/No        | `BOOLEAN`     |
| EnumList      | `TEXT[]`      |
| Ref           | `TEXT` + FK   |

### Columnas Ref (relaciones)

Se almacenan como `TEXT` con FK real en PostgreSQL. AppSheet las usa para navegar relaciones automáticamente igual que en Sheets.

### Nombres de columnas

AppSheet es case-sensitive — los nombres deben coincidir exactamente con los definidos en la app. No renombrar ni cambiar mayúsculas.

### Después de conectar AppSheet a PostgreSQL

1. Ejecutar "Regenerate Structure" para que AppSheet re-escanee los tipos
2. Si un tipo es incorrecto (ej. fecha guardada como TEXT) AppSheet no lo reconocerá bien
3. Probar todas las vistas y acciones en modo preview antes de publicar

---

## Checklist para Nueva App

Pasos a seguir cada vez que se migra una nueva aplicación AppSheet.

### 1. Capturar screenshots de AppSheet antes de crear nada

Antes de escribir una sola línea de SQL, abre AppSheet y toma un screenshot de la estructura de cada tabla (columnas y tipos). Guardarlos en:

```
docs/appsheet_screenshots/<nombre_app>/
```

Esta es la fuente de verdad. Los nombres en AppSheet son los que mandan.

### 2. Crear el SQL con nombres exactos

- Abrir el screenshot de cada tabla
- Escribir cada columna exactamente como aparece en AppSheet
- Respetar mayúsculas, minúsculas, espacios, guiones bajos y caracteres especiales como `%`
- Siempre envolver en comillas dobles en PostgreSQL: `"Nombre columna"`

```sql
-- CORRECTO
"Id_Supervisor"   text NOT NULL
"%Jornada_Bono"   numeric DEFAULT 0
"Centro de Costo" text

-- INCORRECTO — nunca hacer esto
id_supervisor     text NOT NULL
porcentaje_jornada_bono numeric
centro_de_costo   text
```

### 3. Reglas estrictas de nombres

| Regla | Detalle |
|-------|---------|
| NO renombrar | Nunca cambiar a snake_case |
| NO normalizar | Nunca quitar espacios ni caracteres especiales |
| NO traducir | Si AppSheet dice `"Empresa"`, el campo es `"Empresa"` |
| NO asumir | Siempre verificar contra el screenshot |
| NO quitar tildes | Si AppSheet dice `"Bonificación"`, el campo es `"Bonificación"` — con tilde |

### 3.1 Tildes y caracteres especiales en nombres de columna

AppSheet preserva tildes y acentos exactamente como el usuario los definió. El CSV exportado también los incluye. La DB debe coincidir.

**Columnas con tilde confirmadas en contratistas_isla_maipo:**

| Columna en AppSheet/CSV | Columna en DB |
|-------------------------|---------------|
| `Bonificación` | `"Bonificación"` |
| `Valor Bonificación 2` | `"Valor Bonificación 2"` |

**Regla práctica:** si el CSV exportado tiene tilde → la tabla DB debe tener tilde → el INSERT usa tilde → el `row.get()` usa tilde.

```sql
-- CORRECTO
"Bonificación" numeric

-- INCORRECTO — rompe la conexión con AppSheet
"Bonificacion" numeric
```

```python
# CORRECTO — tilde en INSERT y en row.get()
cur.execute(f'INSERT INTO {TABLE} ("Bonificación") VALUES (%s)', (
    clean_currency(row.get("Bonificación")),
))
```

### 4. Columnas `%` y psycopg2

Las columnas que empiezan con `%` (como `%Jornada_Bono`, `%Trato`) requieren manejo especial:

- En el SQL del script Python, usar `%%` para escapar el `%` (psycopg2 trata `%` como placeholder)
- En el `row.get()` del CSV, usar `%` normal porque el CSV tiene el nombre real

```python
# En la query SQL (dentro del f-string) → doble %%
cur.execute(f"""
    INSERT INTO {TABLE} ("%%Jornada_Bono", "%%Trato")
    VALUES (%s, %s)
""", (
    clean_percentage(row.get("%Jornada_Bono")),  # CSV → % normal
    clean_percentage(row.get("%Trato")),
))
```

### 5. Columnas que NUNCA se migran

| Columna | Razón |
|---------|-------|
| `_RowNumber` | Virtual de Google Sheets, no existe en PostgreSQL |
| `Related_*` | AppSheet las genera automáticamente como reverse ref |
| Columnas de fórmula | AppSheet las recalcula, no son datos |

### 6. Orden de carga respeta FKs

Identificar las dependencias entre tablas antes de escribir `load_all.py`. Cargar siempre:
- Primero las tablas sin FK (lookup tables: empresa, labor, cultivos)
- Luego las que dependen de ellas (contratistas → trabajadores → tratos → registro...)

### 7. Loader no normaliza headers

El `core/loader.py` solo hace `.strip()` en los headers del CSV — no transforma ni normaliza. Los headers del CSV de AppSheet ya coinciden con los nombres de columna. No agregar transformaciones.

### 8. Script load_*.py: estructura estándar

```python
from core.cleaners import clean_currency, clean_percentage
from core.db import get_connection
from core.loader import load_csv
from core.utils import get_logger

logger = get_logger("<nombre_app>")
TABLE = "appsheet.<nombre_app>_<tabla>"
CSV = "data/<nombre_app>/raw/<tabla>.csv"

def run():
    df = load_csv(CSV)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute(f"""
                        INSERT INTO {TABLE} ("Col1", "Col2")
                        VALUES (%s, %s)
                        ON CONFLICT ("PK_Col") DO UPDATE SET
                            "Col2" = EXCLUDED."Col2"
                    """, (
                        row.get("Col1") or None,
                        row.get("Col2") or None,
                    ))
        logger.info(f"{TABLE}: {len(df)} rows loaded.")
    finally:
        conn.close()

if __name__ == "__main__":
    run()
```

### 9. Tipos de datos — mapeo

| AppSheet | PostgreSQL | Cleaner |
|----------|-----------|---------|
| Text | `TEXT` | ninguno |
| Number / Decimal | `NUMERIC` | ninguno |
| Price | `NUMERIC` | `clean_currency()` |
| Percent | `NUMERIC` | `clean_percentage()` |
| Date | `DATE` | `clean_date()` |
| DateTime | `TIMESTAMP` | `clean_date()` |
| Yes/No | `BOOLEAN` | `clean_boolean()` |
| EnumList | `TEXT[]` | `clean_enumlist()` |
| Ref | `TEXT` + FK | `row.get()` |

### 10. Validación post-carga

Después de cargar cada tabla, verificar conteos:

```sql
SELECT COUNT(*) FROM appsheet.<nombre_app>_<tabla>;
```

El número debe coincidir con las filas del CSV original.

---

## Proyecto

Migración técnica AppSheet → PostgreSQL
Arquitectura multi-app escalable
