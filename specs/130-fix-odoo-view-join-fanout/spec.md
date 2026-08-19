# Montos duplicados en export a Odoo por JOIN sin límite en tarjas_reporte_odoo
# Path: specs/130-fix-odoo-view-join-fanout/spec.md
issue: #130 · branch: 130-fix-odoo-view-join-fanout · date: 2026-08-19

## What
El Excel de Orden de Compra a Odoo no mostraba líneas incompletas para Bonhomia, M y D y Gutiérrez II (Zuñiga), pero sus montos no cuadraban con el visor en pantalla — algunas labores se exportaban duplicadas.

## Acceptance
- [x] `tarjas_reporte_odoo` nunca produce más filas que `tarjas_reporte` para el mismo contratista/campo/fecha.
- [x] El total del visor (`GET /api/purchase-orders`) coincide con el total del Excel exportado, dentro del margen de redondeo.
- [x] Test de regresión.

## Context
- `appsheet.tarjas_labores` no tiene restricción de unicidad sobre `id_labor` — confirmado: 5 pares de filas comparten `id_labor` (8.3, 8.1, 7.6, 4.2, 5.1), algunos por variantes de puntuación legítimas de la misma labor real (4.2, 5.1 — mismo patrón de #32/#124), otros aparentemente por error de catalogación (8.1: "ASEO Y ORNATO" vs "TALLER Y BODEGA"; 7.6: "HUMIDIFICACIÓN" vs "ENCORDADO" — dos labores distintas compartiendo código).
- Los JOIN `l0`-`l3` de `sql/tarjas/02_views_odoo.sql` eran `LEFT JOIN` planos contra `tarjas_labores`: si una labor matcheaba 2 filas del catálogo (mismo `id_labor`, mismo texto normalizado, o mismo prefijo `[X.Y]`/`X.Y-`), la vista producía 2 filas de salida para esa jornada — el `codigo_labor` resultante era el mismo en ambas, pero la fila (y por lo tanto la jornada/monto) quedaba contada dos veces en el export.
- Caso real confirmado (lectura de producción): `id_labor='8.1'` → "ASEO Y ORNATO" duplicada en `tarjas_reporte_odoo` (57 filas vs 54 en `tarjas_reporte` para Bonhomia/Zuñiga 12–18/08/2026). El exceso calculado ($496.500) coincidió exactamente con la suma de las jornadas duplicadas de esa labor.
- Diferencia repetida en Gutiérrez II ($150.000) — mismo `id_labor='8.1'`, misma labor "ASEO Y ORNATO".

## Decisions
- Fix a nivel de vista, no de datos: cada join `l0`-`l3` pasa a `LEFT JOIN LATERAL (SELECT codigo_labor FROM tarjas_labores WHERE ... LIMIT 1)`, garantizando como máximo 1 fila sin importar cuántas variantes de texto compartan `codigo_labor`. Esto es más robusto que solo limpiar el catálogo (que puede volver a duplicarse, como ya pasó con #124) y no requiere decidir cuál de las 2 filas "gana" — para los pares legítimos (4.2, 5.1) ambas apuntan al mismo `codigo_labor`, así que el resultado es idéntico sin importar cuál elige `LIMIT 1`.
- No se tocó el catálogo `tarjas_labores` en este fix — los pares 8.1 ("ASEO Y ORNATO" vs "TALLER Y BODEGA") y 7.6 ("HUMIDIFICACIÓN" vs "ENCORDADO") parecen ser labores realmente distintas compartiendo `id_labor` por error de carga, lo cual podría estar asignando el `codigo_labor` incorrecto a una de las dos — pero corregir eso requiere confirmar en Odoo cuál es el producto correcto para cada una (fuera de alcance de este fix, que resuelve la duplicación financiera inmediata).
- Vista aplicada directamente en producción (`CREATE OR REPLACE VIEW`, no destructivo) antes de este commit para cerrar el impacto financiero de inmediato; este PR persiste el fix en el repo.

## Implemented
- `sql/tarjas/02_views_odoo.sql` — joins `l0`-`l3` convertidos a `LEFT JOIN LATERAL (...) LIMIT 1`.
- `chatai/tests/test_130_tarjas_odoo_view_no_fanout.py` — 5 tests de regresión contra la BD real.

## Tests
```
pytest chatai/tests/test_130_tarjas_odoo_view_no_fanout.py -v
5 passed in 0.53s
```
Verificado en producción tras aplicar el fix:
- Bonhomia/Zuñiga: filas `tarjas_reporte_odoo` 57 → 54 (igual a `tarjas_reporte`); diff visor/Excel $496.500 → $0.02 (redondeo).
- Gutiérrez II/Zuñiga: diff $150.000 → $0.00.
- M y D/Zuñiga: sin cambio (nunca tuvo el bug), diff $0.05 (redondeo, no relacionado).

## Deferred
- Revisar en Odoo si "TALLER Y BODEGA" (comparte `id_labor='8.1'` con "ASEO Y ORNATO") y "ENCORDADO" (comparte `id_labor='7.6'` con "HUMIDIFICACIÓN") deberían tener su propio `codigo_labor` distinto — son labores diferentes que hoy resuelven al mismo producto Odoo por el `id_labor` compartido. El fix de este issue evita que se dupliquen jornadas, pero no corrige a cuál producto se están imputando.
- Revisar el par `codigo_labor='8.3'` (dos variantes de "MANTENCIÓN INFRAESTRUCTURA") — mismo patrón que 4.2/5.1, probablemente legítimo, sin acción requerida.
