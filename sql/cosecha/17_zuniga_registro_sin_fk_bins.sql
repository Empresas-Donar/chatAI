-- OBSOLETO. No correr: 25_zuniga_registro_crea_bin.sql vuelve a crear la FK.
-- El trigger del registro inserta el bin antes de guardar la fila.
--
-- Cosecha Zúñiga: registro puede guardarse junto con el bin
--
-- La FK a bins obligaba a que el bin existiera antes del registro.
-- AppSheet crea los dos en el mismo guardado, así que la FK se quita.
-- id_bins sigue siendo la relación. El índice se mantiene.
-- No volver a crear cosecha_zuniga_registro_bins_fk.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_registro
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_registro_bins_fk;

CREATE INDEX IF NOT EXISTS ix_registro_id_bins
  ON cosecha_zuniga_registro (id_bins);

COMMENT ON COLUMN cosecha_zuniga_registro.id_bins IS
  'Id de sistema del bin. Sin FK: AppSheet crea bin y registro juntos.';

COMMIT;
