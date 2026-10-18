-- =============================================================================
-- Cosecha Zúñiga: máximo de cuadrillas configurable (default 16)
--
-- La lista del contratista y la cuadrilla hija usan el mismo tope.
-- La fila general de configuracion queda en 16 si nadie lo cambió.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_configuracion
  ADD COLUMN IF NOT EXISTS max_cuadrillas integer NOT NULL DEFAULT 16;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_configuracion_max_chk'
  ) THEN
    ALTER TABLE cosecha_zuniga_configuracion
      ADD CONSTRAINT cosecha_zuniga_configuracion_max_chk
      CHECK (max_cuadrillas >= 1);
  END IF;
END $$;

CREATE OR REPLACE FUNCTION cosecha_valida_max_cuadrillas()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_max int;
  v_bad bigint;
BEGIN
  SELECT COALESCE(MAX(max_cuadrillas), 16) INTO v_max
  FROM cosecha_zuniga_configuracion;

  SELECT MAX(x::bigint) INTO v_bad
  FROM regexp_split_to_table(COALESCE(NEW.cuadrillas, ''), '\s*,\s*') AS x
  WHERE x ~ '^\d+$'
    AND (x::bigint < 1 OR x::bigint > v_max);

  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'La cuadrilla % supera el máximo permitido (%)', v_bad, v_max;
  END IF;

  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_contratistas_valida_max ON cosecha_zuniga_contratistas;
CREATE TRIGGER trg_contratistas_valida_max
  BEFORE INSERT OR UPDATE OF cuadrillas ON cosecha_zuniga_contratistas
  FOR EACH ROW EXECUTE FUNCTION cosecha_valida_max_cuadrillas();

-- Misma regla cuando la app inserta la cuadrilla hija, no la lista.
CREATE OR REPLACE FUNCTION cosecha_valida_numero_cuadrilla()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_otra record;
  v_max int;
BEGIN
  IF current_setting('cosecha.syncing', true) = '1' THEN
    RETURN NEW;
  END IF;

  SELECT COALESCE(MAX(max_cuadrillas), 16) INTO v_max
  FROM cosecha_zuniga_configuracion;

  IF NEW.cuadrilla < 1 OR NEW.cuadrilla > v_max THEN
    RAISE EXCEPTION 'La cuadrilla % supera el máximo permitido (%)', NEW.cuadrilla, v_max;
  END IF;

  SELECT id_contratista
  INTO v_otra
  FROM cosecha_zuniga_cuadrillas
  WHERE cuadrilla = NEW.cuadrilla
    AND id_cuadrilla <> NEW.id_cuadrilla;

  IF FOUND THEN
    IF v_otra.id_contratista IS NULL THEN
      RAISE EXCEPTION
        'La cuadrilla % está libre. Reasígnela en vez de crear otra', NEW.cuadrilla;
    END IF;
    RAISE EXCEPTION 'La cuadrilla % ya pertenece a otro contratista', NEW.cuadrilla;
  END IF;

  RETURN NEW;
END $$;

COMMENT ON COLUMN cosecha_zuniga_configuracion.max_cuadrillas IS
  'Número más alto de cuadrilla que la app puede guardar. Default 16.';

COMMIT;
