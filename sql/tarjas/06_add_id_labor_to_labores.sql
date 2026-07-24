-- =============================================================================
-- TARJAS: Agregar columna id_labor a tarjas_labores
-- Issue #35: la vista tarjas_reporte_odoo hace JOIN con l0.id_labor pero la
-- columna no existia en tarjas_labores. Se agrega como columna generada que
-- replica codigo_labor (ya que tarjas_pagos.id_labor almacena codigo_labor).
--
-- Idempotente: usa ADD COLUMN IF NOT EXISTS.
-- Ejecutar antes que 02_views_odoo.sql.
-- =============================================================================

ALTER TABLE appsheet.tarjas_labores
    ADD COLUMN IF NOT EXISTS id_labor TEXT GENERATED ALWAYS AS (codigo_labor) STORED;
