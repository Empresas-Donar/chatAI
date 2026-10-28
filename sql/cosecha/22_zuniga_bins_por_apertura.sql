-- =============================================================================
-- Cosecha Zúñiga: una fila de bins por cada apertura de cajón
--
-- id_bins es la clave. bins es el número y se puede repetir.
-- registro.id_bins y escaneo.id_bins guardan la clave, nunca el número.
-- escaneo.bins es text y registro.bins es integer: la copia va como texto.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE TABLE IF NOT EXISTS bk_20261018_bins AS
  SELECT * FROM cosecha_zuniga_bins;

CREATE TABLE IF NOT EXISTS bk_20261018_registro AS
  SELECT * FROM cosecha_zuniga_registro;

CREATE TABLE IF NOT EXISTS bk_20261018_escaneo AS
  SELECT * FROM cosecha_zuniga_escaneo;

CREATE TEMP TABLE m ON COMMIT DROP AS
SELECT r.id_registro,
       r.id_bins AS id_bins_viejo,
       COALESCE(
         (SELECT b.bins FROM cosecha_zuniga_bins b
           WHERE b.id_bins = r.id_bins AND r.id_bins !~ '^\d+$'),
         NULLIF(regexp_replace(COALESCE(r.bins::text, r.id_bins), '[^0-9]', '', 'g'), '')::integer
       ) AS numero,
       substr(md5(random()::text || clock_timestamp()::text || r.id_registro), 1, 8) AS id_bins_nuevo
FROM cosecha_zuniga_registro r
WHERE r.id_bins ~ '^\d+$'
   OR NOT EXISTS (SELECT 1 FROM cosecha_zuniga_bins b WHERE b.id_bins = r.id_bins)
   OR r.id_registro <> (
        SELECT min(r2.id_registro)
        FROM cosecha_zuniga_registro r2
        WHERE r2.id_bins = r.id_bins
      );

INSERT INTO cosecha_zuniga_bins (id_bins, bins)
SELECT id_bins_nuevo, numero FROM m;

UPDATE cosecha_zuniga_registro r
SET id_bins = m.id_bins_nuevo,
    bins    = m.numero
FROM m
WHERE r.id_registro = m.id_registro;

UPDATE cosecha_zuniga_escaneo e
SET id_bins = r.id_bins,
    bins    = r.bins::text
FROM cosecha_zuniga_registro r
WHERE e.id_registro = r.id_registro
  AND (e.id_bins IS DISTINCT FROM r.id_bins OR e.bins IS DISTINCT FROM r.bins::text);

DELETE FROM cosecha_zuniga_bins b
WHERE b.id_bins ~ '^\d+$'
  AND NOT EXISTS (SELECT 1 FROM cosecha_zuniga_registro r WHERE r.id_bins = b.id_bins)
  AND NOT EXISTS (SELECT 1 FROM cosecha_zuniga_escaneo e WHERE e.id_bins = b.id_bins);

COMMIT;
