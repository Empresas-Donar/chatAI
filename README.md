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

## Proyecto

Migración técnica AppSheet → PostgreSQL
Arquitectura multi-app escalable
