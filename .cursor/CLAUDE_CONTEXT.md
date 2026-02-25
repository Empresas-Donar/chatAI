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