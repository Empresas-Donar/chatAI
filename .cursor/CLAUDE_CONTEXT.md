# Claude Context

Project: AppSheet → PostgreSQL Migration Toolkit

This is a scalable migration framework.

We support multiple apps:
- contratistas_isla_maipo (tarjas / mano de obra)
- cosecha_isla_de_maipo y cosecha_zuniga (escaneo de capachos; ver abajo)
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

## App de cosecha (`cosecha_*`)

Dos apps AppSheet ya migradas a `appsheet`, una por predio. No hay código en el repo (ni controlador, ni vistas, ni SQL). Distinta de tarjas y de `despacho_ingreso`.

Tablas (mismo set en ambos predios): `escaneo`, `registro`, `qr`, `tratos`, `cuarteles`, `contratistas`, `usuarios`, `bins`.

- `cosecha_isla_de_maipo_*` — Isla de Maipo
- `cosecha_zuniga_*` — Zúñiga

Grano:

- 1 fila de `escaneo` = 1 capacho. Pago observado: `COUNT(*) × precio_trato_aplicado` (CLP). `piso_aplicado` es el piso diario en CLP.
- `bins` es el **número del bin**, no una cantidad. No usar `SUM(bins)`. Las tablas `*_bins` están vacías.
- `registro` abre el bin (una fila por bin). `registro.bins` es el mismo id.
- `tratos.precio_capacho` es el precio vigente; el escaneo lo congela en `precio_trato_aplicado`.
- `escaneo.codigo_qr` (`cos;` + código) = `qr.qr_trabajador`.
- `escaneo.cuartel` = `cuarteles.nombre_cuartel`. `registro.cuartel` = `cuarteles.id_cuartel`.
- En Isla, `contratistas.cuadrillas` es el número de cuadrilla, no un conteo. En Zúñiga, `contratistas` es una fila por contratista y `cosecha_zuniga_cuadrillas` es la hija (`sql/cosecha/01_zuniga_cuadrillas.sql`). La columna `contratistas.cuadrillas` de Zúñiga está obsoleta y en NULL. El número es único dentro del contratista y puede repetirse entre contratistas. Registro, QR y escaneo guardan el nombre, no el id.
- `usuarios.contraseña` es secreto en texto plano. No seleccionarla.

No aplicar factores de Costo Empresa (1.45 / 1.50). Eso es solo tarjas.

Deriva entre predios (no normalizar nombres):

- Isla `escaneo.bins` es NUMERIC; Zúñiga es TEXT (incluye `'Manual'`).
- Isla el día sin hora es `"Fecha_Solo_Dia"` (comillar). Zúñiga es `fecha_solo_dia`.
- Isla `tratos.piso_garantizado_diario` es INTEGER. Zúñiga es BOOLEAN (el piso se perdió).
- Isla `registro.fecha_y_hora` y `tratos.fecha_inicio_vigencia` son TEXT. Zúñiga usa TIMESTAMP / DATE.
- Isla y el resto de tablas de Zúñiga siguen sin PK, FK ni índices. Excepción: `cosecha_zuniga_contratistas` y `cosecha_zuniga_cuadrillas`. Hay ids duplicados en filas incompletas.

Datos con escaneo (revisión 2026-10-01): Isla, cereza Rainier 27–28 nov 2025 (~2.000 capachos, $700, piso $15.000). Zúñiga, ciruela D'Agen 22–29 ene 2026 (~21.000 capachos, precio 1.300 → 1.000). El catálogo de cuarteles es más amplio que los días cosechados.