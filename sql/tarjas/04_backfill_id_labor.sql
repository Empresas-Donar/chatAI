-- =============================================================================
-- TARJAS: Backfill tarjas_pagos.id_labor desde tarjas_labores
-- Issue #27: la columna id_labor fue agregada pero todos los valores son NULL.
--
-- Estrategias de match (en orden de prioridad):
--   l1 → nombre exacto normalizado (espacios múltiples colapsados)
--   l2 → prefijo [X.Y] en el nombre: "[2.1]AMARRA" → codigo_labor = "2.1"
--   l3 → prefijo X.Y- en el nombre:  "1.3-REPLANTE" → codigo_labor = "1.3"
--
-- Idempotente: solo actualiza filas con id_labor IS NULL.
-- Para filas nuevas usar el trigger 05_trigger_id_labor.sql (automático).
-- =============================================================================

UPDATE appsheet.tarjas_pagos p
SET id_labor = COALESCE(
    -- l1: nombre exacto normalizado
    (SELECT l.codigo_labor
     FROM appsheet.tarjas_labores l
     WHERE trim(l.labor) = trim(p.labor)
     ORDER BY l.id
     LIMIT 1),

    -- l2: prefijo [X.Y] en el nombre
    (SELECT l.codigo_labor
     FROM appsheet.tarjas_labores l
     WHERE p.labor ~ '^\[[\d.]+\]'
       AND l.codigo_labor = trim(SUBSTRING(p.labor FROM '^\[([\d.]+)\]'))
     LIMIT 1),

    -- l3: prefijo X.Y- en el nombre
    (SELECT l.codigo_labor
     FROM appsheet.tarjas_labores l
     WHERE p.labor ~ '^[\d]+\.[\d]+-'
       AND l.codigo_labor = trim(SUBSTRING(p.labor FROM '^([\d]+\.[\d]+)-'))
     LIMIT 1)
)
WHERE p.id_labor IS NULL
  AND p.labor IS NOT NULL
  AND trim(p.labor) != '';
