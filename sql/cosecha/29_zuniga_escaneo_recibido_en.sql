-- =============================================================================
-- Cosecha Zúñiga: cuándo llegó el escaneo al servidor
--
-- fecha_y_hora es la hora del teléfono. recibido_en la pone la base
-- al insertar, para ver la demora entre el escaneo y la llegada.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_escaneo
  ADD COLUMN IF NOT EXISTS recibido_en timestamptz;

CREATE OR REPLACE FUNCTION set_recibido_en()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
BEGIN
  NEW.recibido_en := now();
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_escaneo_recibido ON cosecha_zuniga_escaneo;
CREATE TRIGGER trg_escaneo_recibido
  BEFORE INSERT ON cosecha_zuniga_escaneo
  FOR EACH ROW EXECUTE FUNCTION set_recibido_en();

COMMENT ON COLUMN cosecha_zuniga_escaneo.recibido_en IS
  'Hora en que la base recibió el escaneo. La llena el trigger al insertar.';

COMMIT;
