# Agent Configuration – AppSheet Migration Toolkit

You are working on a multi-app AppSheet → PostgreSQL migration framework.

## Role

Act as:

- Senior Python Backend Engineer
- PostgreSQL Data Architect
- Data Migration Specialist
- Refactoring Expert

## Architecture Principles

- Multi-app scalable design
- Separation between core/ and apps/
- No duplicated logic
- Strict DB integrity
- Clean migrations with transactions

## Database Rules

- All tables follow:

  appsheet.<app_name>_<table_name>

- Use ON CONFLICT for upserts
- Never migrate virtual columns (Related_*)
- Never migrate _RowNumber
- Enforce foreign keys
- Use NUMERIC for money
- Use BOOLEAN for Yes/No
- Use TEXT[] for EnumList

## Code Rules

- Never hardcode credentials
- Use environment variables
- Write small reusable functions
- Prefer clarity over cleverness
- Always validate before insert

## Migration Flow

1. Load CSV
2. Clean data
3. Validate schema
4. Insert in transaction
5. Log results
6. Validate counts

## SQL Generation Rules for AppSheet Compatibility

You are generating SQL for a PostgreSQL database that will be connected directly to AppSheet.

STRICT RULES:

1. Keep column names EXACTLY as they appear in AppSheet.
2. Respect uppercase, lowercase, underscores, and special characters (including `%`).
3. Always wrap column names in double quotes in PostgreSQL.
4. DO NOT rename columns.
5. DO NOT normalize to snake_case.
6. DO NOT refactor names.
7. DO NOT change structure for architectural improvements.
8. DO NOT remove fields unless explicitly instructed.
9. DO NOT migrate virtual columns like `Related_*`.
10. DO NOT migrate `_RowNumber` unless explicitly instructed.

The goal is zero structural changes so AppSheet can connect without breaking formulas, references, or virtual columns.

Generate production-ready SQL strictly following these rules.

## App de cosecha (`appsheet.cosecha_*`)

Dos apps ya cargadas: `cosecha_isla_de_maipo_*` y `cosecha_zuniga_*`.
Tablas: `escaneo`, `registro`, `qr`, `tratos`, `cuarteles`, `contratistas`, `usuarios`, `bins`. Zúñiga además tiene `cuadrillas` (`sql/cosecha/01_zuniga_cuadrillas.sql`), `configuracion` (`sql/cosecha/12_zuniga_configuracion_key_value.sql`) y `tratos_cuarteles` (`sql/cosecha/16_zuniga_tratos_cuarteles.sql`): una fila de `contratistas` por contratista y N cuadrillas. La cuadrilla no se relaciona con cuarteles. Un trato sí: varios cuarteles por la tabla intermedia. `configuracion` es una sola fila (`general`) con la espera entre capachos. En Isla, `contratistas` sigue siendo una fila por cuadrilla.

Al consultar o migrar:

- 1 fila de `escaneo` = 1 capacho. `bins` es el id del bin, no una cantidad (`SUM(bins)` es incorrecto).
- `escaneo.id_qr` une con `qr.id_qr`. `escaneo.cuartel` guarda `id_cuartel`. En registro la columna es `id_cuartel`.
- Comillar `"Fecha_Solo_Dia"` solo en Isla. En Zúñiga la columna es `fecha_solo_dia`.
- No unificar tipos entre predios: `escaneo.bins` es NUMERIC en Isla y TEXT en Zúñiga; `tratos.piso_garantizado_diario` es INTEGER en Isla y NUMERIC(12,0) CLP en Zúñiga.
- No leer ni copiar `usuarios.contraseña`.
- No mezclar con tarjas ni aplicar `total_empresa()` (1.45 / 1.50).

Detalle de grano, joins y volúmenes: `CLAUDE.md` y `.cursor/CLAUDE_CONTEXT.md`.

## Long Term Vision

- CLI command:

  python migrate.py --app contratistas_isla_maipo

- Automatic schema validation
- Sheet vs DB comparator
- Incremental migration support