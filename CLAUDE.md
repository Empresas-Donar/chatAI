# AppSheet → PostgreSQL Migration Toolkit

## Contexto del Proyecto

Framework para migrar múltiples aplicaciones AppSheet a PostgreSQL.

Apps actuales:
- `contratistas_isla_maipo`
- `medicion_pozos`

Convención de tablas: `appsheet.<nombre_app>_<nombre_tabla>`

Ejemplos:
```
appsheet.contratistas_isla_maipo_contratistas
appsheet.medicion_pozos_ingresos
```

---

## Arquitectura

```
core/     → lógica reutilizable (db, cleaners, loader, utils)
apps/     → scripts específicos por app
sql/      → definición de esquemas por app
data/     → CSV raw y procesados por app
logs/     → salidas de migración
```

No mezclar responsabilidades entre capas. La lógica reutilizable siempre va en `core/`.

---

## Language Convention

All code must be written in English:
- File names, variable names, function names, class names
- Comments, docstrings, log messages, git commit messages

Exception: table names, column names, and CSV field names stay in Spanish
as defined by the client (e.g. `id_trabajador`, `contratista`, `fecha_inicio_trato`).
Do not translate these — they must match the AppSheet source exactly.

---

## Reglas de Desarrollo

1. No hardcodear credenciales — usar variables de entorno (`.env`)
2. Usar funciones reutilizables en `core/`
3. Validar tipos antes de insertar en DB
4. Usar `ON CONFLICT` (UPSERT) siempre — nunca INSERT sin manejo de duplicados
5. Evitar duplicación de código entre apps
6. Mantener funciones pequeñas y testeables
7. Documentar scripts críticos

---

## Limpieza de Datos

Aplicar siempre estas transformaciones antes de insertar:

| Entrada      | Salida         |
|--------------|----------------|
| `$18.000`    | `18000`        |
| `45,00%`     | `0.45`         |
| Fechas       | `YYYY-MM-DD`   |
| Boolean      | `True`/`False` |
| EnumList     | `TEXT[]`       |

---

## AppSheet + PostgreSQL Conventions

**Primary Keys**
- Always `TEXT NOT NULL PRIMARY KEY` — never `SERIAL` or `INTEGER`
- AppSheet generates its own string IDs; the column name must match exactly what AppSheet uses as Row ID

**Columns to NEVER migrate**
- `_RowNumber` — virtual Sheets column, does not exist in PostgreSQL
- `Related_*` — reverse ref virtual columns, AppSheet generates these automatically
- Any AppSheet formula/virtual columns

**Type Mapping**
| AppSheet type | PostgreSQL type |
|---|---|
| Text | `TEXT` |
| Number / Decimal / Price | `NUMERIC` |
| Date | `DATE` |
| DateTime | `TIMESTAMP` |
| Yes/No | `BOOLEAN` |
| EnumList | `TEXT[]` |
| Ref | `TEXT` (FK to the referenced table's PK) |

**Ref columns (relationships)**
- Store as `TEXT` with a real FK constraint
- AppSheet uses these to navigate relationships automatically

**Column names**
- AppSheet is case-sensitive — column names must match exactly what AppSheet expects
- Never rename, add spaces, or change casing

**After connecting AppSheet to PostgreSQL**
- Run "Regenerate Structure" so AppSheet re-scans types
- If a column type is wrong (e.g. date stored as TEXT), AppSheet will not recognize it correctly
- Test all views and actions in preview mode before going live

## Revisión de SQL

Al generar o revisar SQL:

- Validar foreign keys y orden de creación de tablas
- Usar `NUMERIC` para dinero/porcentajes, no `TEXT`
- Nunca migrar columnas virtuales de AppSheet
- Nunca migrar columnas `Related_*`

---

## Flujo de Migración

1. Analizar CSV de entrada
2. Aplicar limpieza automática (`core/cleaners.py`)
3. Insertar con transacción
4. Loggear resultados
5. Validar conteos finales

---

## Orden de Migración (dependencias)

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

## Futuro

- CLI central: `python migrate.py --app nombre_app`
- Validación automática de esquemas
- Comparador Sheet vs DB
- Migraciones incrementales
