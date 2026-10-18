-- =============================================================================
-- Cosecha Zúñiga: id de sistema del bin
--
-- El código (1212, 1313) puede repetirse, así que no es la clave.
-- id_bins es un id de 8 caracteres, uno por cada apertura en registro.
-- registro.bins y escaneo.bins conservan el código.
--
-- No hay FK de registro ni de escaneo hacia bins.
-- 17 y 20 las quitan: AppSheet guarda bin, registro y escaneo juntos.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_registro
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_registro_bins_fk;

ALTER TABLE cosecha_zuniga_bins
  ADD COLUMN IF NOT EXISTS bins integer;

ALTER TABLE cosecha_zuniga_escaneo
  ADD COLUMN IF NOT EXISTS id_bins text;

INSERT INTO cosecha_zuniga_bins (id_bins, bins)
SELECT substr(md5('bin:' || r.id_registro), 1, 8), r.bins
FROM cosecha_zuniga_registro r
WHERE r.bins IS NOT NULL
ON CONFLICT (id_bins) DO UPDATE
SET bins = EXCLUDED.bins;

UPDATE cosecha_zuniga_registro r
SET id_bins = substr(md5('bin:' || r.id_registro), 1, 8)
WHERE r.bins IS NOT NULL;

UPDATE cosecha_zuniga_escaneo e
SET id_bins = r.id_bins
FROM cosecha_zuniga_registro r
WHERE r.id_registro = e.id_registro
  AND r.id_bins IS NOT NULL;

DELETE FROM cosecha_zuniga_bins b
WHERE NOT EXISTS (
  SELECT 1 FROM cosecha_zuniga_registro r WHERE r.id_bins = b.id_bins
);

-- Sin FK a bins. Ver 17_zuniga_registro_sin_fk_bins.sql y
-- 20_zuniga_escaneo_sin_fk_bins.sql.

CREATE INDEX IF NOT EXISTS ix_escaneo_id_bins
  ON cosecha_zuniga_escaneo (id_bins);

COMMENT ON COLUMN cosecha_zuniga_bins.id_bins IS
  'Id de sistema. El código en bins puede repetirse.';

COMMENT ON COLUMN cosecha_zuniga_bins.bins IS
  'Código del bin, por ejemplo 1212. No es único.';

COMMENT ON COLUMN cosecha_zuniga_registro.id_bins IS
  'Ref a cosecha_zuniga_bins. El código sigue en bins.';

COMMENT ON COLUMN cosecha_zuniga_escaneo.id_bins IS
  'Mismo id de sistema que el registro del bin.';

COMMIT;
