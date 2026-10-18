-- =============================================================================
-- Cosecha Zúñiga: el QR no guarda el nombre del contratista
--
-- El contratista sale de id_contratista. La columna de texto sobra.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_qr
  DROP COLUMN IF EXISTS contratista;

COMMIT;
