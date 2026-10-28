-- =============================================================================
-- Cosecha Zúñiga: el registro crea su bin
--
-- AppSheet manda id_bins (UNIQUEID) y bins (el número escaneado).
-- Antes de guardar el registro, este trigger crea la fila en bins
-- con el trato vigente del cuartel a esa fecha.
-- Sin trato, el registro se rechaza y no queda bin.
-- escaneo.bins es text: el número se copia como texto.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_bins
  ADD COLUMN IF NOT EXISTS id_trato text;

ALTER TABLE cosecha_zuniga_escaneo
  ADD COLUMN IF NOT EXISTS id_trato text;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'cosecha_zuniga_bins_trato_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_bins
      ADD CONSTRAINT cosecha_zuniga_bins_trato_fk
      FOREIGN KEY (id_trato) REFERENCES cosecha_zuniga_tratos (id_trato);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'cosecha_zuniga_escaneo_trato_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_escaneo
      ADD CONSTRAINT cosecha_zuniga_escaneo_trato_fk
      FOREIGN KEY (id_trato) REFERENCES cosecha_zuniga_tratos (id_trato);
  END IF;
END $$;

CREATE OR REPLACE FUNCTION cosecha_trato_para(p_cuartel text, p_fecha date)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = appsheet, pg_catalog
AS $$
  SELECT t.id_trato
  FROM cosecha_zuniga_tratos t
  JOIN cosecha_zuniga_tratos_cuarteles tc ON tc.id_trato = t.id_trato
  WHERE tc.id_cuartel = p_cuartel
    AND t.fecha_inicio_vigencia <= p_fecha
  ORDER BY t.fecha_inicio_vigencia DESC
  LIMIT 1
$$;

CREATE OR REPLACE FUNCTION cosecha_registro_bin()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_trato text;
BEGIN
  IF NEW.id_bins IS NULL OR NEW.id_bins = '' THEN
    RAISE EXCEPTION 'El registro no trae id_bins';
  END IF;
  IF NEW.bins IS NULL THEN
    RAISE EXCEPTION 'Falta el código del bin';
  END IF;

  v_trato := cosecha_trato_para(NEW.id_cuartel, NEW.fecha_y_hora::date);
  IF v_trato IS NULL THEN
    RAISE EXCEPTION
      'No hay trato vigente para el cuartel % al %',
      NEW.id_cuartel, NEW.fecha_y_hora::date;
  END IF;

  INSERT INTO cosecha_zuniga_bins (id_bins, bins, id_trato)
  VALUES (NEW.id_bins, NEW.bins, v_trato)
  ON CONFLICT (id_bins) DO UPDATE
    SET bins = EXCLUDED.bins,
        id_trato = EXCLUDED.id_trato;

  IF TG_OP = 'UPDATE' THEN
    UPDATE cosecha_zuniga_escaneo
    SET id_trato = v_trato,
        bins = NEW.bins::text
    WHERE id_bins = NEW.id_bins
      AND (
        id_trato IS DISTINCT FROM v_trato
        OR bins IS DISTINCT FROM NEW.bins::text
      );
  END IF;

  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_cosecha_registro_trato ON cosecha_zuniga_registro;
DROP TRIGGER IF EXISTS trg_cosecha_registro_bin ON cosecha_zuniga_registro;
CREATE TRIGGER trg_cosecha_registro_bin
  BEFORE INSERT OR UPDATE OF id_bins, bins, id_cuartel, fecha_y_hora
  ON cosecha_zuniga_registro
  FOR EACH ROW EXECUTE FUNCTION cosecha_registro_bin();

CREATE OR REPLACE FUNCTION cosecha_escaneo_trato()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
BEGIN
  SELECT b.id_trato, b.bins::text
    INTO NEW.id_trato, NEW.bins
  FROM cosecha_zuniga_bins b
  WHERE b.id_bins = NEW.id_bins;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_cosecha_escaneo_trato ON cosecha_zuniga_escaneo;
CREATE TRIGGER trg_cosecha_escaneo_trato
  BEFORE INSERT OR UPDATE OF id_bins ON cosecha_zuniga_escaneo
  FOR EACH ROW EXECUTE FUNCTION cosecha_escaneo_trato();

DROP TRIGGER IF EXISTS trg_cosecha_bins_trato ON cosecha_zuniga_bins;
DROP FUNCTION IF EXISTS cosecha_bins_trato();
DROP FUNCTION IF EXISTS cosecha_registro_trato();

UPDATE cosecha_zuniga_bins b
SET id_trato = cosecha_trato_para(r.id_cuartel, r.fecha_y_hora::date)
FROM cosecha_zuniga_registro r
WHERE r.id_bins = b.id_bins;

UPDATE cosecha_zuniga_escaneo e
SET id_trato = b.id_trato
FROM cosecha_zuniga_bins b
WHERE b.id_bins = e.id_bins
  AND e.id_trato IS DISTINCT FROM b.id_trato;

ALTER TABLE cosecha_zuniga_registro
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_registro_bins_fk;

ALTER TABLE cosecha_zuniga_registro
  ADD CONSTRAINT cosecha_zuniga_registro_bins_fk
  FOREIGN KEY (id_bins) REFERENCES cosecha_zuniga_bins (id_bins) NOT VALID;

ALTER TABLE cosecha_zuniga_escaneo
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_escaneo_bins_fk;

ALTER TABLE cosecha_zuniga_escaneo
  ADD CONSTRAINT cosecha_zuniga_escaneo_bins_fk
  FOREIGN KEY (id_bins) REFERENCES cosecha_zuniga_bins (id_bins) NOT VALID;

COMMIT;
