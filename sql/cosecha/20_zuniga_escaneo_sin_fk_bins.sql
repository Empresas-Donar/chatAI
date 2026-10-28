-- OBSOLETO. No correr: 25_zuniga_registro_crea_bin.sql vuelve a crear la FK.
-- El escaneo hereda un bin que el registro ya creó.
--
-- Cosecha Zúñiga: el escaneo puede guardarse junto con el bin
--
-- La FK a bins obligaba a que el bin existiera antes del escaneo.
-- AppSheet crea los dos en el mismo guardado, así que la FK se quita.
-- id_bins sigue siendo la relación. El índice se mantiene.
-- No volver a crear cosecha_zuniga_escaneo_bins_fk.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_escaneo
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_escaneo_bins_fk;

CREATE INDEX IF NOT EXISTS ix_escaneo_id_bins
  ON cosecha_zuniga_escaneo (id_bins);

COMMENT ON COLUMN cosecha_zuniga_escaneo.id_bins IS
  'Id de sistema del bin. Sin FK: AppSheet crea bin y escaneo juntos.';

COMMIT;
