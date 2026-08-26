# PDF Resumen por Persona: orden alfabético y nombre duplicado
# Path: specs/137-resumen-persona-alfabetico/spec.md
issue: #137 · branch: 137-resumen-persona-alfabetico · date: 2026-08-26

## What
El PDF de "Resumen por persona" ahora ordena a los trabajadores alfabéticamente y muestra el nombre de cada uno una sola vez, agrupando sus filas "Al día" y "trato" debajo, igual que la pantalla "Detalle trabajador".

## Acceptance
- [x] Las personas aparecen ordenadas alfabéticamente por nombre en el PDF
- [x] El nombre del trabajador aparece una sola vez, sin importar si tiene línea "Al día", "trato", o ambas
- [x] El PDF unificado de `/reportes` hereda el mismo cambio (comparten `_build_resumen_persona_html` desde el issue #116)

## Context
- Módulo: `chatai/backend/controllers/tarjas_controller.py`, función `_build_resumen_persona_html` (compartida entre el endpoint standalone y el PDF masivo de `/reportes`).
- El issue #134 (PR #135) ya había convertido este PDF a formato pivot (una columna por fecha, nombre impreso solo en la primera fila de cada trabajador vía la bandera `is_first`, comparando contra la fila anterior con `prev != trab`).
- La causa de este bug: `sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])` ordenaba por el total de cada combinación (trabajador, tipo_pago) de forma descendente. Como el total de la línea "Al día" y el de "trato" de un mismo trabajador casi nunca son iguales, ambas filas podían quedar separadas por filas de otros trabajadores con un total intermedio — rompiendo la contigüidad que `is_first` necesita, y mostrando el nombre repetido en vez de una sola vez.
- Valores reales de `tipo_pago` en la BD: `"Al dia"` / `"Al día"` y `"trato"` (confirmado en `_TIPO_PAGO_LABELS`, línea ~757). El orden alfabético natural de estos strings ya coloca "Al dia"/"Al día" antes que "trato" (mayúscula `A` < minúscula `t` en comparación de strings), consistente con la captura de pantalla compartida por el usuario.

## Decisions
- Orden: `key=lambda x: ((x[0][0] or "").lower(), x[0][1] or "")` — nombre del trabajador en minúsculas (alfabético, insensible a mayúsculas) como clave primaria, `tipo_pago` tal cual como clave secundaria (mantiene "Al dia" antes de "trato" y agrupa las filas del mismo trabajador de forma contigua, lo cual además arregla el bug de nombre duplicado).
- No se tocó `_TIPO_PAGO_LABELS` ni el resto del render — el pedido es solo de orden/agrupamiento, no de formato visual.

## Implemented
### Backend
- `chatai/backend/controllers/tarjas_controller.py`: `_build_resumen_persona_html()` — cambia el criterio de orden de `sorted_workers` de total descendente a (trabajador alfabético, tipo_pago).

### Tests
- `chatai/tests/test_137_resumen_persona_orden_alfabetico.py` — verifica que los trabajadores aparecen en orden alfabético en el HTML generado y que cada nombre aparece exactamente una vez aunque tenga filas "Al día" y "trato".

## Routes
Sin cambios de rutas.

## Tests
```
pytest tests/test_137_resumen_persona_orden_alfabetico.py tests/test_134_resumen_persona_pdf_pivot.py -v
8 passed

pytest tests/ -q
311 passed, 2 failed (test_50_odoo_export_tractorista.py — preexistente, no relacionado)
```
Se confirmó que el test de orden alfabético falla con el código anterior (revertido temporalmente) y pasa con el fix aplicado.

## Manual QA
1. Descargar el PDF de "Resumen por persona" con un rango de fechas que incluya varios trabajadores con líneas "Al día" y "trato" — confirmar que están en orden alfabético.
2. Confirmar que cada trabajador aparece una sola vez, con sus filas agrupadas debajo (igual que la captura de la pantalla "Detalle trabajador").
3. Descargar el mismo reporte desde el PDF unificado de `/reportes` — debe verse idéntico.
