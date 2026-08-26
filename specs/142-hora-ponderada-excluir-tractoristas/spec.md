# Reporte Hora ponderada 9h incluye labores de tractoristas
# Path: specs/142-hora-ponderada-excluir-tractoristas/spec.md
issue: #142 · branch: 142-hora-ponderada-excluir-tractoristas · date: 2026-08-26

## What
El reporte "Hora ponderada estandarizada a 9 horas" ahora excluye toda tarja con `tipo_pago='tractorista'`, tanto en los datos del pivote como en los dropdowns de filtro — solo quedan labores de campo.

## Acceptance
- [x] Los datos del pivote (`/api/tarjas/hora-ponderada-9h`, Excel, PDF) no incluyen ninguna fila con tipo_pago='tractorista'.
- [x] Los dropdowns de filtro (Contratista/Empresa/CC/Labor) no ofrecen valores que solo existen en filas tractoristas (ej. labor "Jornada Tractor simple").
- [x] Sin regresión en otros reportes de tarjas.

## Context
- Reporte implementado en `chatai/backend/controllers/tarjas_controller.py`, funciones `_build_hora_ponderada_filters` (línea ~4151) y `get_tarjas_hora_ponderada_filters` (línea ~4213), que consultan `appsheet.tarjas_pagos` directamente (no la vista `tarjas_reporte`) — ver spec `specs/102-weighted-hourly-rate-9h/spec.md`.
- El resto del sistema ya identifica filas de tractorista con la constante compartida `_TRACTORISTA_PAGOS_SQL = "(LOWER(TRIM(tipo_pago)) = 'tractorista')"` (línea 68), usada en los reportes dedicados `*-tractorista` (para incluir SOLO esas filas). Este fix usa la misma constante negada (`NOT _TRACTORISTA_PAGOS_SQL`) para excluirlas.
- Verificado contra la BD real: 176 de 3.748 filas de `tarjas_pagos` son tractorista (labores "Hora Extra", "Jornada Tractor normal", "Jornada Tractor simple", "OPERARIO SOLO"), quedan 3.572 filas de campo.

## Decisions
- La exclusión se agregó como filtro incondicional (no como opción de UI) porque el pedido es que este reporte sea exclusivamente de labores de campo, sin excepción.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`: `_build_hora_ponderada_filters` agrega `NOT _TRACTORISTA_PAGOS_SQL` al WHERE base; `get_tarjas_hora_ponderada_filters` agrega el mismo criterio a las 4 consultas de distinct values (contratista, cuartel_cc, labor, empresas).

### Tests
- `chatai/tests/test_142_hora_ponderada_excluir_tractoristas.py` (nuevo)

## Routes
Sin cambios de rutas — mismos endpoints `/api/tarjas/hora-ponderada-9h`, `/api/tarjas/hora-ponderada-9h/filters` y sus exports.

## Tests
```
pytest tests/test_142_hora_ponderada_excluir_tractoristas.py tests/ -k tarja -v
28 passed (tarjas) + 3 passed (nuevo) in ~16s
```
Cross-farm isolation: N/A (reporte ya filtra por contratista/campo vía query params, sin cambios ahí).

## Manual QA
1. Ir a Catálogo de Reportes → Tarjas → Contratistas → "Hora ponderada estandarizada a 9 horas".
2. Confirmar que el dropdown de Labor ya no muestra "Jornada Tractor simple", "Jornada Tractor normal", "Hora Extra" ni "OPERARIO SOLO".
3. Consultar un rango de fechas amplio y confirmar que ninguna fila del pivote corresponde a esas labores.
4. Descargar Excel y PDF del mismo filtro y confirmar que tampoco aparecen ahí.

## Deferred
- No se tocó ningún otro reporte de tarjas.
