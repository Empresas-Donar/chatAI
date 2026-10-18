-- =============================================================================
-- Cosecha Zúñiga: cultivo del cuartel
--
-- cereza en todos, salvo CC-860 CIRUELOS ADULTOS (C06), que es ciruela.
-- Los id no se mueven: registro y tratos ya apuntan a ellos.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_cuarteles
  ADD COLUMN IF NOT EXISTS cultivo text;

UPDATE cosecha_zuniga_cuarteles
SET cultivo = CASE
  WHEN id_cuartel = 'C06'
    OR nombre_cuartel ILIKE '%CIRUELO%'
    THEN 'ciruela'
  ELSE 'cereza'
END;

UPDATE cosecha_zuniga_cuarteles
SET variedad = 'D''Agen'
WHERE id_cuartel = 'C06'
  AND variedad IS DISTINCT FROM 'D''Agen';

ALTER TABLE cosecha_zuniga_cuarteles
  ALTER COLUMN cultivo SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_cuarteles_cultivo_chk'
  ) THEN
    ALTER TABLE cosecha_zuniga_cuarteles
      ADD CONSTRAINT cosecha_zuniga_cuarteles_cultivo_chk
      CHECK (cultivo IN ('cereza', 'ciruela'));
  END IF;
END $$;

COMMENT ON COLUMN cosecha_zuniga_cuarteles.cultivo IS
  'cereza o ciruela. Ciruela solo en CC-860 CIRUELOS ADULTOS.';

COMMIT;
