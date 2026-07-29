-- =============================================================================
-- TARJAS: Resincronizar tarjas_pagos.id_labor cuando quedó desactualizado
-- Issue #58
--
-- El trigger trg_set_id_labor (issue #27, 05_trigger_id_labor.sql) solo
-- recalcula id_labor en INSERT o UPDATE OF labor. Si tarjas_labores.codigo_labor
-- se corrige DESPUÉS de que una fila de tarjas_pagos ya tiene id_labor fijado,
-- esa fila nunca se resincroniza automáticamente — el backfill original
-- (04_backfill_id_labor.sql) tampoco la toca porque solo cubre id_labor IS NULL.
--
-- Caso confirmado: id_Resumen='87ae12dc' (SUPERVISOR HUERTO, HERBI ML SPA,
-- Isla de Maipo, 23 julio 2026) tenía id_labor='9.10' mientras
-- tarjas_labores.codigo_labor='9.1' para esa misma labor — causaba que la
-- fila quedara sin product_id (product_id NULL) en tarjas_reporte_odoo,
-- marcada "Incompleta" en la vista previa de exportación a Odoo.
--
-- Este script es el complemento general de 04_backfill_id_labor.sql: en vez
-- de solo llenar NULLs, resincroniza cualquier fila donde el id_labor actual
-- ya no coincide con el codigo_labor vigente para su texto de labor exacto.
--
-- Idempotente: solo actualiza filas con desajuste real.
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_pagos p
SET id_labor = l.codigo_labor
FROM appsheet.tarjas_labores l
WHERE trim(l.labor) = trim(p.labor)
  AND p.id_labor IS DISTINCT FROM l.codigo_labor;

COMMIT;
