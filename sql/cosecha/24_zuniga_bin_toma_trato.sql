-- =============================================================================
-- Cosecha Zúñiga: el bin toma el trato por el cuartel de su registro
--
-- Trato vigente = fecha_inicio_vigencia más reciente <= fecha del registro
-- y cuyo tratos_cuarteles incluye el cuartel del registro.
-- Si no hay trato, id_trato queda NULL. No se rechaza el registro.
-- El bin puede nacer antes que el registro: el trigger del bin lo completa.
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

CREATE OR REPLACE FUNCTION cosecha_registro_trato()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_trato text;
BEGIN
  v_trato := cosecha_trato_para(NEW.id_cuartel, NEW.fecha_y_hora::date);

  UPDATE cosecha_zuniga_bins
  SET id_trato = v_trato
  WHERE id_bins = NEW.id_bins
    AND id_trato IS DISTINCT FROM v_trato;

  UPDATE cosecha_zuniga_escaneo
  SET id_trato = v_trato
  WHERE id_bins = NEW.id_bins
    AND id_trato IS DISTINCT FROM v_trato;

  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_cosecha_registro_trato ON cosecha_zuniga_registro;
CREATE TRIGGER trg_cosecha_registro_trato
  AFTER INSERT OR UPDATE OF id_bins, id_cuartel, fecha_y_hora
  ON cosecha_zuniga_registro
  FOR EACH ROW EXECUTE FUNCTION cosecha_registro_trato();

CREATE OR REPLACE FUNCTION cosecha_bins_trato()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
BEGIN
  IF NEW.id_trato IS NULL THEN
    SELECT cosecha_trato_para(r.id_cuartel, r.fecha_y_hora::date)
      INTO NEW.id_trato
    FROM cosecha_zuniga_registro r
    WHERE r.id_bins = NEW.id_bins
    LIMIT 1;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_cosecha_bins_trato ON cosecha_zuniga_bins;
CREATE TRIGGER trg_cosecha_bins_trato
  BEFORE INSERT OR UPDATE ON cosecha_zuniga_bins
  FOR EACH ROW EXECUTE FUNCTION cosecha_bins_trato();

CREATE OR REPLACE FUNCTION cosecha_escaneo_trato()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
BEGIN
  SELECT b.id_trato INTO NEW.id_trato
  FROM cosecha_zuniga_bins b
  WHERE b.id_bins = NEW.id_bins;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_cosecha_escaneo_trato ON cosecha_zuniga_escaneo;
CREATE TRIGGER trg_cosecha_escaneo_trato
  BEFORE INSERT OR UPDATE OF id_bins ON cosecha_zuniga_escaneo
  FOR EACH ROW EXECUTE FUNCTION cosecha_escaneo_trato();

UPDATE cosecha_zuniga_bins b
SET id_trato = cosecha_trato_para(r.id_cuartel, r.fecha_y_hora::date)
FROM cosecha_zuniga_registro r
WHERE r.id_bins = b.id_bins;

UPDATE cosecha_zuniga_escaneo e
SET id_trato = b.id_trato
FROM cosecha_zuniga_bins b
WHERE b.id_bins = e.id_bins
  AND e.id_trato IS DISTINCT FROM b.id_trato;

COMMIT;
