-- =============================================================================
-- Cosecha Zúñiga: registro, QR y escaneo exigen cuadrilla y contratista
--
-- Solo aplicar con esas columnas ya pobladas. Una fila vacía aborta el ALTER.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_registro
  ALTER COLUMN id_cuadrilla SET NOT NULL,
  ALTER COLUMN id_contratista SET NOT NULL;

ALTER TABLE cosecha_zuniga_qr
  ALTER COLUMN id_cuadrilla SET NOT NULL,
  ALTER COLUMN id_contratista SET NOT NULL;

ALTER TABLE cosecha_zuniga_escaneo
  ALTER COLUMN id_cuadrilla SET NOT NULL,
  ALTER COLUMN id_contratista SET NOT NULL;

COMMIT;
