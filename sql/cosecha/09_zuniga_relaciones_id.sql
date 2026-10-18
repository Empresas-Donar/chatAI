-- =============================================================================
-- Cosecha Zúñiga: relaciones por id
--
-- Escaneo  -> id_registro, id_qr, id_cuadrilla, id_contratista.
--             cuartel pasa a id_cuartel (el del bin).
-- Registro -> id_cuadrilla. contratista y cuartel guardan el id.
-- QR       -> id_cuadrilla, id_contratista.
--
-- bins, cuadrilla, contratista, trabajador y rut_trabajador se conservan
-- como copia. La app ya no las usa para relacionar.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE TABLE IF NOT EXISTS bk_20261014_registro AS
SELECT * FROM cosecha_zuniga_registro;

CREATE TABLE IF NOT EXISTS bk_20261014_escaneo AS
SELECT * FROM cosecha_zuniga_escaneo;

CREATE TABLE IF NOT EXISTS bk_20261014_qr AS
SELECT * FROM cosecha_zuniga_qr;

CREATE OR REPLACE FUNCTION cosecha_num(v anyelement) RETURNS numeric
LANGUAGE sql IMMUTABLE
SET search_path = appsheet, pg_catalog
AS $$
  SELECT CASE
    WHEN trim(v::text) ~ '^\d+(\.\d+)?$' THEN trim(v::text)::numeric
  END
$$;

ALTER TABLE cosecha_zuniga_registro ADD COLUMN IF NOT EXISTS id_cuadrilla   text;
ALTER TABLE cosecha_zuniga_qr       ADD COLUMN IF NOT EXISTS id_cuadrilla   text;
ALTER TABLE cosecha_zuniga_qr       ADD COLUMN IF NOT EXISTS id_contratista text;
ALTER TABLE cosecha_zuniga_escaneo  ADD COLUMN IF NOT EXISTS id_registro    text;
ALTER TABLE cosecha_zuniga_escaneo  ADD COLUMN IF NOT EXISTS id_qr          text;
ALTER TABLE cosecha_zuniga_escaneo  ADD COLUMN IF NOT EXISTS id_cuadrilla   text;
ALTER TABLE cosecha_zuniga_escaneo  ADD COLUMN IF NOT EXISTS id_contratista text;

UPDATE cosecha_zuniga_registro r
SET id_cuadrilla = c.id_cuadrilla
FROM cosecha_zuniga_cuadrillas c
WHERE r.id_cuadrilla IS NULL
  AND cosecha_num(c.cuadrilla) = cosecha_num(r.cuadrilla);

UPDATE cosecha_zuniga_registro r
SET contratista = ct.id_contratista
FROM cosecha_zuniga_contratistas ct
WHERE r.contratista::text = ct.contratistas::text
  AND r.contratista::text <> ct.id_contratista::text;

UPDATE cosecha_zuniga_registro r
SET contratista = c.id_contratista
FROM cosecha_zuniga_cuadrillas c
WHERE c.id_cuadrilla = r.id_cuadrilla
  AND c.id_contratista IS NOT NULL
  AND (r.contratista IS NULL OR r.contratista::text = '');

UPDATE cosecha_zuniga_registro r
SET cuartel = cu.id_cuartel
FROM cosecha_zuniga_cuarteles cu
WHERE r.cuartel::text = cu.nombre_cuartel::text
  AND r.cuartel::text <> cu.id_cuartel::text;

UPDATE cosecha_zuniga_qr q
SET id_cuadrilla = c.id_cuadrilla
FROM cosecha_zuniga_cuadrillas c
WHERE q.id_cuadrilla IS NULL
  AND cosecha_num(c.cuadrilla) = cosecha_num(q.cuadrilla);

UPDATE cosecha_zuniga_qr q
SET id_contratista = ct.id_contratista
FROM cosecha_zuniga_contratistas ct
WHERE q.id_contratista IS NULL
  AND (q.contratista::text = ct.contratistas::text
       OR q.contratista::text = ct.id_contratista::text);

UPDATE cosecha_zuniga_qr q
SET id_contratista = c.id_contratista
FROM cosecha_zuniga_cuadrillas c
WHERE q.id_contratista IS NULL
  AND c.id_cuadrilla = q.id_cuadrilla;

UPDATE cosecha_zuniga_escaneo e
SET id_cuadrilla = c.id_cuadrilla
FROM cosecha_zuniga_cuadrillas c
WHERE e.id_cuadrilla IS NULL
  AND cosecha_num(c.cuadrilla) = cosecha_num(e.cuadrilla);

UPDATE cosecha_zuniga_escaneo e
SET id_contratista = c.id_contratista
FROM cosecha_zuniga_cuadrillas c
WHERE e.id_contratista IS NULL
  AND c.id_cuadrilla = e.id_cuadrilla;

UPDATE cosecha_zuniga_escaneo e
SET id_qr = q.id_qr
FROM cosecha_zuniga_qr q
WHERE e.id_qr IS NULL
  AND q.qr_trabajador::text = e.codigo_qr::text;

UPDATE cosecha_zuniga_escaneo e
SET id_registro = (
  SELECT r.id_registro
  FROM cosecha_zuniga_registro r
  WHERE r.bins::text = e.bins::text
    AND (r.id_cuadrilla = e.id_cuadrilla OR e.id_cuadrilla IS NULL)
  ORDER BY (r.fecha_y_hora <= e.fecha_y_hora) DESC,
           abs(extract(epoch FROM (e.fecha_y_hora - r.fecha_y_hora)))
  LIMIT 1)
WHERE e.id_registro IS NULL
  AND e.bins IS NOT NULL;

UPDATE cosecha_zuniga_escaneo e
SET cuartel = r.cuartel
FROM cosecha_zuniga_registro r
WHERE r.id_registro = e.id_registro
  AND e.cuartel::text IS DISTINCT FROM r.cuartel::text;

CREATE INDEX IF NOT EXISTS ix_escaneo_id_registro
  ON cosecha_zuniga_escaneo (id_registro);
CREATE INDEX IF NOT EXISTS ix_escaneo_id_qr
  ON cosecha_zuniga_escaneo (id_qr);
CREATE INDEX IF NOT EXISTS ix_escaneo_id_cuadrilla
  ON cosecha_zuniga_escaneo (id_cuadrilla);
CREATE INDEX IF NOT EXISTS ix_registro_id_cuadrilla
  ON cosecha_zuniga_registro (id_cuadrilla);
CREATE INDEX IF NOT EXISTS ix_qr_id_cuadrilla
  ON cosecha_zuniga_qr (id_cuadrilla);

COMMIT;
