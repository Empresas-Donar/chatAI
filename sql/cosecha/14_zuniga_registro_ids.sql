-- =============================================================================
-- Cosecha Zúñiga: el registro relaciona por id
--
-- contratista ya guardaba el id del contratista.
-- cuartel ya guardaba el id del cuartel.
-- Se renombran. id_cuadrilla e id_bins ya existían.
-- cuadrilla y bins siguen siendo el número y el código.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_registro
  RENAME COLUMN contratista TO id_contratista;

ALTER TABLE cosecha_zuniga_registro
  RENAME COLUMN cuartel TO id_cuartel;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_registro_contratista_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_registro
      ADD CONSTRAINT cosecha_zuniga_registro_contratista_fk
      FOREIGN KEY (id_contratista)
      REFERENCES cosecha_zuniga_contratistas (id_contratista);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_registro_cuartel_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_registro
      ADD CONSTRAINT cosecha_zuniga_registro_cuartel_fk
      FOREIGN KEY (id_cuartel)
      REFERENCES cosecha_zuniga_cuarteles (id_cuartel);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_registro_cuadrilla_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_registro
      ADD CONSTRAINT cosecha_zuniga_registro_cuadrilla_fk
      FOREIGN KEY (id_cuadrilla)
      REFERENCES cosecha_zuniga_cuadrillas (id_cuadrilla);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_registro_id_contratista
  ON cosecha_zuniga_registro (id_contratista);

CREATE INDEX IF NOT EXISTS ix_registro_id_cuartel
  ON cosecha_zuniga_registro (id_cuartel);

COMMENT ON COLUMN cosecha_zuniga_registro.id_contratista IS
  'Ref a cosecha_zuniga_contratistas.';

COMMENT ON COLUMN cosecha_zuniga_registro.id_cuartel IS
  'Ref a cosecha_zuniga_cuarteles. El nombre sigue en nombre_cuartel_texto.';

COMMIT;
