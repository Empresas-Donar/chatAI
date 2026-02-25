# Claude Context

Project: AppSheet → PostgreSQL Migration Toolkit

This is a scalable migration framework.

We support multiple apps:
- contratistas_isla_maipo
- medicion_pozos
- future agricultural systems

We prioritize:

- Clean SQL
- Referential integrity
- Idempotent migrations
- Production-ready architecture

Never generate quick hacks.
Always think in scalable patterns.

## Language Convention

All code must be written in English:
- File names (e.g. `load_empresa.py`, `load_all.py`)
- Variable names, function names, class names
- Comments and docstrings
- Log messages
- Git commit messages

Exception: table names, column names, and CSV field names stay in Spanish
as defined by the client (e.g. `id_trabajador`, `contratista`, `fecha_inicio_trato`).
Do not translate these — they must match the AppSheet source exactly.

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