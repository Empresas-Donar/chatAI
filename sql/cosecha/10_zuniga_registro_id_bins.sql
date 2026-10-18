-- =============================================================================
-- Cosecha Zúñiga: el registro apunta al bin por id
--
-- OBSOLETO como clave: el código del bin se repite. El id de sistema está
-- en sql/cosecha/11_zuniga_bins_id_sistema.sql.
--
-- registro.bins sigue siendo el número. id_bins es la relación con
-- cosecha_zuniga_bins.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'cosecha_zuniga_bins'::regclass
      AND contype = 'p'
  ) THEN
    ALTER TABLE cosecha_zuniga_bins
      ADD CONSTRAINT cosecha_zuniga_bins_pkey
      PRIMARY KEY (id_bins);
  END IF;
END $$;

INSERT INTO cosecha_zuniga_bins (id_bins)
SELECT DISTINCT bins::text
FROM cosecha_zuniga_registro
WHERE bins IS NOT NULL
ON CONFLICT (id_bins) DO NOTHING;

INSERT INTO cosecha_zuniga_bins (id_bins)
SELECT DISTINCT btrim(bins)
FROM cosecha_zuniga_escaneo
WHERE bins IS NOT NULL
  AND btrim(bins) <> ''
ON CONFLICT (id_bins) DO NOTHING;

ALTER TABLE cosecha_zuniga_registro
  ADD COLUMN IF NOT EXISTS id_bins text;

UPDATE cosecha_zuniga_registro
SET id_bins = bins::text
WHERE id_bins IS NULL
  AND bins IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_registro_bins_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_registro
      ADD CONSTRAINT cosecha_zuniga_registro_bins_fk
      FOREIGN KEY (id_bins)
      REFERENCES cosecha_zuniga_bins (id_bins);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_registro_id_bins
  ON cosecha_zuniga_registro (id_bins);

COMMENT ON COLUMN cosecha_zuniga_registro.id_bins IS
  'Ref a cosecha_zuniga_bins. bins conserva el número.';

COMMIT;
