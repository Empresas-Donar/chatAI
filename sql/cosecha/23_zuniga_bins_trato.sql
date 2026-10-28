-- =============================================================================
-- Cosecha Zúñiga: cada apertura de bin apunta a un trato
--
-- id_trato es la relación. El número del cajón sigue en bins.
-- Queda nullable: el bin ya abierto no tiene un trato que asignarle.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_bins
  ADD COLUMN IF NOT EXISTS id_trato text;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_bins_trato_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_bins
      ADD CONSTRAINT cosecha_zuniga_bins_trato_fk
      FOREIGN KEY (id_trato)
      REFERENCES cosecha_zuniga_tratos (id_trato);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_bins_id_trato
  ON cosecha_zuniga_bins (id_trato);

COMMENT ON COLUMN cosecha_zuniga_bins.id_trato IS
  'Ref a cosecha_zuniga_tratos. El precio de esta apertura.';

COMMIT;
