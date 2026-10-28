-- =============================================================================
-- Cosecha Zúñiga: recrear escaneo
--
-- La tabla fue eliminada. La copia bk_20261018_escaneo es anterior al
-- reset y apunta a cuadrillas que ya no existen, así que no se restauran
-- esas filas. Se deja la tabla lista para escanear de nuevo.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE TABLE cosecha_zuniga_escaneo (
  LIKE bk_20261018_escaneo INCLUDING DEFAULTS
);

ALTER TABLE cosecha_zuniga_escaneo
  ADD COLUMN id_trato text;

ALTER TABLE cosecha_zuniga_escaneo
  ALTER COLUMN id_cuadrilla SET NOT NULL,
  ALTER COLUMN id_contratista SET NOT NULL;

ALTER TABLE cosecha_zuniga_escaneo
  ADD CONSTRAINT cosecha_zuniga_escaneo_trato_fk
  FOREIGN KEY (id_trato) REFERENCES cosecha_zuniga_tratos (id_trato);

ALTER TABLE cosecha_zuniga_escaneo
  ADD CONSTRAINT cosecha_zuniga_escaneo_bins_fk
  FOREIGN KEY (id_bins) REFERENCES cosecha_zuniga_bins (id_bins);

CREATE INDEX ix_escaneo_id_bins ON cosecha_zuniga_escaneo (id_bins);

DROP TRIGGER IF EXISTS trg_cosecha_escaneo_trato ON cosecha_zuniga_escaneo;
CREATE TRIGGER trg_cosecha_escaneo_trato
  BEFORE INSERT OR UPDATE OF id_bins ON cosecha_zuniga_escaneo
  FOR EACH ROW EXECUTE FUNCTION cosecha_escaneo_trato();

COMMENT ON COLUMN cosecha_zuniga_escaneo.id_trato IS
  'Lo llena el trigger desde el bin.';

COMMENT ON COLUMN cosecha_zuniga_escaneo.precio_trato_aplicado IS
  'Precio del capacho copiado del trato al escanear.';

COMMENT ON COLUMN cosecha_zuniga_escaneo.piso_aplicado IS
  'Piso diario copiado del trato al escanear.';

COMMIT;
