-- =============================================================================
-- Cosecha Zúñiga: cuadrilla ↔ cuartel (varios a varios)
--
-- Una cuadrilla trabaja N cuarteles. El mismo cuartel puede estar en otra
-- cuadrilla. La pareja (cuadrilla, cuartel) no se repite.
--
-- AppSheet guarda el padre primero y después los hijos, así que la base no
-- exige cuarteles en el mismo INSERT de la cuadrilla. En el formulario de
-- la app la relación va como tabla hija obligatoria.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet;

ALTER TABLE cosecha_zuniga_cuarteles
  ALTER COLUMN "id_cuartel" SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_cuarteles_pkey'
  ) THEN
    ALTER TABLE cosecha_zuniga_cuarteles
      ADD CONSTRAINT cosecha_zuniga_cuarteles_pkey
      PRIMARY KEY ("id_cuartel");
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS cosecha_zuniga_cuadrilla_cuartel (
  "id_cuadrilla_cuartel" text      PRIMARY KEY,
  "id_cuadrilla"         text      NOT NULL,
  "id_cuartel"           text      NOT NULL,
  "fecha_y_hora"         timestamp NOT NULL DEFAULT now()
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_cuadrilla_cuartel_cuadrilla_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_cuadrilla_cuartel
      ADD CONSTRAINT cosecha_zuniga_cuadrilla_cuartel_cuadrilla_fk
      FOREIGN KEY ("id_cuadrilla")
      REFERENCES cosecha_zuniga_cuadrillas ("id_cuadrilla")
      ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_cuadrilla_cuartel_cuartel_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_cuadrilla_cuartel
      ADD CONSTRAINT cosecha_zuniga_cuadrilla_cuartel_cuartel_fk
      FOREIGN KEY ("id_cuartel")
      REFERENCES cosecha_zuniga_cuarteles ("id_cuartel")
      ON DELETE RESTRICT;
  END IF;
END $$;

-- La misma cuadrilla no lista dos veces el mismo cuartel.
CREATE UNIQUE INDEX IF NOT EXISTS cosecha_zuniga_cuadrilla_cuartel_par_uq
  ON cosecha_zuniga_cuadrilla_cuartel ("id_cuadrilla", "id_cuartel");

-- El cuartel sí puede repetirse en otra cuadrilla. Este índice es solo de búsqueda.
CREATE INDEX IF NOT EXISTS cosecha_zuniga_cuadrilla_cuartel_cuartel_idx
  ON cosecha_zuniga_cuadrilla_cuartel ("id_cuartel");

COMMENT ON TABLE cosecha_zuniga_cuadrilla_cuartel IS
  'Cuarteles que trabaja una cuadrilla. El mismo id_cuartel puede estar en varias cuadrillas.';

COMMENT ON COLUMN cosecha_zuniga_cuadrilla_cuartel."id_cuadrilla" IS
  'Ref a cosecha_zuniga_cuadrillas. En AppSheet es parte de la cuadrilla.';

COMMENT ON COLUMN cosecha_zuniga_cuadrilla_cuartel."id_cuartel" IS
  'Ref a cosecha_zuniga_cuarteles (id_cuartel, por ejemplo C01).';

COMMIT;
