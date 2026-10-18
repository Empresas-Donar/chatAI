-- =============================================================================
-- Cosecha Zúñiga: un trato puede cubrir varios cuarteles
--
-- cosecha_zuniga_tratos_cuarteles es la tabla intermedia.
-- id_trato no tenía clave: se agrega para que la relación pueda apuntar.
-- cuartel_id y nombre_cuartel quedan en el trato, ya sin obligación.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'cosecha_zuniga_tratos'::regclass
      AND contype = 'p'
  ) THEN
    ALTER TABLE cosecha_zuniga_tratos
      ALTER COLUMN id_trato SET NOT NULL;
    ALTER TABLE cosecha_zuniga_tratos
      ADD CONSTRAINT cosecha_zuniga_tratos_pkey
      PRIMARY KEY (id_trato);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS cosecha_zuniga_tratos_cuarteles (
  id_trato_cuartel text PRIMARY KEY,
  id_trato   text NOT NULL
    REFERENCES cosecha_zuniga_tratos (id_trato) ON DELETE CASCADE,
  id_cuartel text NOT NULL
    REFERENCES cosecha_zuniga_cuarteles (id_cuartel),
  CONSTRAINT uq_trato_cuartel UNIQUE (id_trato, id_cuartel)
);

CREATE INDEX IF NOT EXISTS ix_tratos_cuarteles_cuartel
  ON cosecha_zuniga_tratos_cuarteles (id_cuartel);

INSERT INTO cosecha_zuniga_tratos_cuarteles (id_trato_cuartel, id_trato, id_cuartel)
SELECT substr(md5(random()::text || t.id_trato), 1, 8), t.id_trato, t.cuartel_id
FROM cosecha_zuniga_tratos t
WHERE t.cuartel_id IS NOT NULL
  AND t.cuartel_id <> ''
ON CONFLICT DO NOTHING;

ALTER TABLE cosecha_zuniga_tratos
  ALTER COLUMN cuartel_id DROP NOT NULL,
  ALTER COLUMN nombre_cuartel DROP NOT NULL;

COMMIT;
