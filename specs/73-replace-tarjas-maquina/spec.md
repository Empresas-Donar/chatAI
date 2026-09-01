# Reemplazar catálogo tarjas_maquina con columnas nuevas (color, patente, tractorista, campo)
# Path: specs/73-replace-tarjas-maquina/spec.md
issue: #73 · branch: 73-replace-tarjas-maquina · date: 2026-07-31

## What
`appsheet.tarjas_maquina` se reemplazó completamente: se agregaron las columnas `color`, `patente`, `tractorista`, `campo`, se borraron las 15 filas anteriores y se insertaron las 18 filas nuevas provistas por el usuario. La granularidad cambió de "una fila por máquina" a "una fila por máquina y campo donde está desplegada".

## Acceptance
- [x] Se agregan las columnas nuevas: `color`, `patente`, `tractorista`, `campo`
- [x] Se borran las filas actuales y se insertan las 18 filas nuevas provistas por el usuario
- [x] La clave única pasa a ser (`id_maquina`, `campo`) — verificado que no hay duplicados en los datos nuevos
- [x] Tests de regresión que verifican el conteo final y la unicidad de (id_maquina, campo)

## Context
- Tabla sin PK ni FK antes de este cambio, sin referencias desde `chatai/backend/` (`grep -rn "tarjas_maquina" backend/` no arrojó resultados) — reemplazo seguro, no rompe ningún endpoint existente.
- Columnas previas: `id_maquina`, `maquina`, `"año"` (texto libre, ej. "2019"), `cumple` (SI/NO) — 15 filas, una por `id_maquina`.
- El usuario aportó los datos en dos capturas de pantalla; la primera tenía la columna "Maquina" cortada visualmente, se pidió una segunda captura completa antes de tocar la base de datos.

## Decisions
- **(id_maquina, campo) como clave natural**, no `id_maquina` solo — verificado antes de insertar que las 18 filas nuevas no tienen ningún par (id_maquina, campo) repetido. No se agregó una constraint `PRIMARY KEY` formal (la tabla nunca tuvo una y no se pidió explícitamente).
- **`"año"` se guarda como TEXT con la fecha completa** tal como viene en la planilla (ej. `'01/01/2026'`), no solo el año — la columna ya era TEXT antes, sin conflicto de tipo; consistente con la convención del proyecto de guardar fechas de AppSheet como texto libre.
- **Celdas "Cumple" en blanco → NULL** (patentes RLXJ64 y SJWB50), no un valor por defecto — se preserva la ambigüedad tal cual el usuario la entregó, en vez de asumir SI o NO.
- **Inconsistencia detectada y preservada, no corregida**: `id_maquina='3aa5e989'` aparece como "Massey Ferguson 250" en campo 1 y 2, pero como "Massey 265" en campo 3 — mismo ID de máquina, dos nombres distintos según el campo. Se flageó al usuario antes de ejecutar; el usuario confirmó la tabla tal cual (segunda captura, idéntica en este punto a la primera), por lo que se cargó sin modificar.
- **Dos ids nuevos, muy parecidos a ids existentes, confirmados como intencionales** (no typos): `48d46934` (vs. el preexistente `48d46933` = "New Holland") y `3aa5e990` (vs. el preexistente `3aa5e989`) — confirmado porque el usuario repitió exactamente los mismos valores en ambas capturas.

## Implemented
### SQL
- `sql/tarjas/16_replace_tarjas_maquina.sql` — `ALTER TABLE` (4 columnas nuevas, todas `TEXT` nullable) + `DELETE` + 18 `INSERT`. **Ya ejecutado contra la BD real.**

### Tests
- `chatai/tests/test_73_replace_tarjas_maquina.py` — 7 tests: columnas nuevas existen, conteo final = 18, (id_maquina, campo) sin duplicados, campo 1 tiene 5 máquinas y campo 2 tiene 4 (comparten todas menos "Same Frutteto 65"), campo 3 tiene 9, los 2 ids nuevos están presentes, las celdas "Cumple" en blanco quedaron NULL.

## Routes
N/A — tabla de catálogo sin endpoints propios en este repo.

## Tests
```
pytest tests/test_73_replace_tarjas_maquina.py -v
7 passed in 2.21s

pytest tests/ -v
200 passed, 2 failed in 24.46s
```
Los 2 fallos (`test_50_odoo_export_tractorista.py`) son preexistentes en `main`, no relacionados con este fix.

Cross-farm isolation: N/A — tabla de catálogo global, no segmentada por campo/tenant en el sentido de aislamiento de datos de otros clientes.

## Manual QA
1. `SELECT * FROM appsheet.tarjas_maquina ORDER BY campo, id_maquina` → deben verse 18 filas con las 8 columnas (incluidas color/patente/tractorista/campo).
2. Confirmar con el usuario si la inconsistencia "Massey Ferguson 250" (campo 1/2) vs "Massey 265" (campo 3) para el mismo `id_maquina` es intencional o un error de la planilla origen que deba corregirse en un fix de seguimiento.

## Deferred
- No se agregó una constraint `PRIMARY KEY (id_maquina, campo)` formal — si se decide que esta tabla debe empezar a usarse desde el backend (hoy no tiene ningún endpoint), convendría agregarla en ese momento.
- La inconsistencia de nombre para `id_maquina='3aa5e989'` (Massey Ferguson 250 vs Massey 265) quedó preservada tal cual, no corregida — requiere confirmación del usuario/equipo de operaciones sobre cuál nombre es el correcto.
