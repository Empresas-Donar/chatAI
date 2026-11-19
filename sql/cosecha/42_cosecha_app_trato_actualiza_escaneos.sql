-- =============================================================================
-- Cosecha app: al corregir el trato, se actualizan sus capachos
--
-- El escaneo congela precio y piso. Si después cambian el trato general,
-- esos capachos se quedaban con la copia vieja y la planilla no veía el piso.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE OR REPLACE FUNCTION cosecha_app_trato_actualiza_escaneos()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
BEGIN
  IF NEW.precio_capacho IS DISTINCT FROM OLD.precio_capacho
     OR NEW.piso_garantizado_diario IS DISTINCT FROM OLD.piso_garantizado_diario THEN
    UPDATE cosecha_app_escaneo
    SET precio_trato_aplicado = NEW.precio_capacho,
        piso_aplicado = NEW.piso_garantizado_diario
    WHERE id_trato = NEW.id_trato
      AND (
        precio_trato_aplicado IS DISTINCT FROM NEW.precio_capacho
        OR piso_aplicado IS DISTINCT FROM NEW.piso_garantizado_diario
      );
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_cosecha_app_trato_actualiza_escaneos ON cosecha_app_tratos;
CREATE TRIGGER trg_cosecha_app_trato_actualiza_escaneos
  AFTER UPDATE OF precio_capacho, piso_garantizado_diario
  ON cosecha_app_tratos
  FOR EACH ROW
  EXECUTE FUNCTION cosecha_app_trato_actualiza_escaneos();

COMMENT ON FUNCTION cosecha_app_trato_actualiza_escaneos() IS
  'Al cambiar precio o piso del trato, los copia a los capachos de ese trato.';

COMMIT;
