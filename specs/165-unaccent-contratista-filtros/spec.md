# Spec #165 — fix: contratistas con tilde aparecen duplicados en filtros de dropdown

## What

Los endpoints de filtros de tarjas hacen `SELECT DISTINCT contratista ORDER BY contratista`.
PostgreSQL trata "GUTIERREZ" y "GUTIÉRREZ" como valores distintos, por lo que ambos aparecen
en el dropdown aunque se refieran al mismo contratista. El usuario ve duplicados y al seleccionar
uno, las tarjas del otro quedaban excluidas del reporte.

La extensión `unaccent` de PostgreSQL normaliza acentos en tiempo de consulta sin modificar los
datos. `DISTINCT ON (unaccent(contratista))` agrupa las variantes y conserva la versión canónica
(primera en orden `unaccent`, `contratista`).

## Acceptance criteria (desde el issue)

1. Los dropdowns de contratista en todos los reportes de tarjas muestran cada contratista una sola
   vez, sin importar si hay registros con y sin tilde.
2. El orden del dropdown es alfabético ignorando acentos.
3. La normalización es solo a nivel de presentación — los datos en DB no se modifican.

## Context

Archivos involucrados:
- `chatai/backend/controllers/tarjas_controller.py` — 6 endpoints con `SELECT DISTINCT contratista`:
  - `get_tarjas_general_filters` (~línea 480)
  - `get_tarjas_filters` (~línea 672)
  - `get_tarjas_contractor_filters` (~línea 1507)
  - `get_tarjas_contractor_tractorista_filters` (~línea 1629)
  - `get_tarjas_resumen_persona_filters` (~línea 1777)
  - `get_tarjas_resumen_horas_filters` (~línea 2009)
  - `get_tarjas_resumen_persona_tractorista_filters` (~línea 2139)

La extensión `unaccent` ya está instalada en PostgreSQL y ya se usó para corregir los datos
(11 filas de GUTIERREZ normalizadas). El fix equivalente en `purchase_orders_controller.py`
se incluyó en issue #163.

## Decisions

- Se usa `DISTINCT ON (unaccent(contratista))` + `ORDER BY unaccent(contratista), contratista`
  en lugar de un `LOWER()` o normalización en Python, para mantener la coherencia con el patrón
  ya establecido en `purchase_orders_controller.py`.
- No se modifica la lógica de filtrado de las consultas de datos — solo el endpoint de filters.

## Implemented

- `chatai/backend/controllers/tarjas_controller.py` — 7 consultas de filtros actualizadas con
  `DISTINCT ON (unaccent(contratista))` y `ORDER BY unaccent(contratista), contratista`

## Tests

Sin tests nuevos — la normalización de acentos es una transformación SQL determinista.
Los tests de regresión existentes no dependen del orden del dropdown.

## Manual QA

1. Abrir cualquier reporte de tarjas (ej. Tarjas General) y desplegar el filtro de Contratista.
   Verificar que "GUTIERREZ HERMANOS" aparece una sola vez (no dos entradas con y sin tilde).
2. Seleccionar ese contratista y ejecutar el reporte — verificar que los datos incluyen todas
   sus tarjas (con o sin tilde en el nombre).
3. Repetir en Tarjas Detalle, Tarjas Contratista y Tarjas Resumen Persona.
