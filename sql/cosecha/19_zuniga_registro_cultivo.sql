-- =============================================================================
-- Cosecha Zúñiga: cultivo en el registro
--
-- Copia el cultivo del cuartel cuando el registro ya lo tiene.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_registro
  ADD COLUMN IF NOT EXISTS cultivo text;

UPDATE cosecha_zuniga_registro r
SET cultivo = c.cultivo
FROM cosecha_zuniga_cuarteles c
WHERE c.id_cuartel = r.id_cuartel
  AND r.cultivo IS NULL;

COMMENT ON COLUMN cosecha_zuniga_registro.cultivo IS
  'cereza o ciruela, copiado del cuartel.';

COMMIT;
