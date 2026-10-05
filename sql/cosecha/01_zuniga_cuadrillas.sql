-- =============================================================================
-- Cosecha Zúñiga: un contratista, N cuadrillas
--
-- cosecha_zuniga_contratistas  → 1 fila por contratista
-- cosecha_zuniga_cuadrillas    → tabla hija
--
-- Idempotente. La columna "cuadrillas" del padre se conserva (AppSheet) pero
-- queda en NULL: el número vive en la hija. No se crea un único global del
-- número, porque el mismo número puede existir en dos contratistas.
-- Registro, QR y escaneo guardan el nombre, no el id: no se les agrega FK.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet;

CREATE TABLE IF NOT EXISTS cosecha_zuniga_contratistas_bak AS
SELECT * FROM cosecha_zuniga_contratistas;

ALTER TABLE cosecha_zuniga_contratistas
  ADD COLUMN IF NOT EXISTS "comentario" text;

ALTER TABLE cosecha_zuniga_contratistas
  ALTER COLUMN "cuadrillas" DROP NOT NULL;

CREATE TABLE IF NOT EXISTS cosecha_zuniga_cuadrillas (
  "id_cuadrilla"   text      PRIMARY KEY,
  "id_contratista" text      NOT NULL,
  "cuadrilla"      integer   NOT NULL,
  "fecha_y_hora"   timestamp NOT NULL DEFAULT now()
);

-- Una fila de contratistas por nombre exacto. La hija reutiliza el id viejo.
CREATE TEMP TABLE _mapa_contratistas ON COMMIT DROP AS
SELECT c."id_contratista"::text AS id_viejo,
       first_value(c."id_contratista"::text) OVER (
         PARTITION BY c."contratistas"
         ORDER BY c."fecha_y_hora" NULLS LAST, c."id_contratista"
       ) AS id_nuevo,
       c."cuadrillas",
       c."fecha_y_hora"
FROM cosecha_zuniga_contratistas c;

INSERT INTO cosecha_zuniga_cuadrillas (
  "id_cuadrilla", "id_contratista", "cuadrilla", "fecha_y_hora"
)
SELECT m.id_viejo, m.id_nuevo, m."cuadrillas"::integer, COALESCE(m."fecha_y_hora", now())
FROM _mapa_contratistas m
WHERE m."cuadrillas" IS NOT NULL
ON CONFLICT ("id_cuadrilla") DO NOTHING;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'cosecha_zuniga_registro',
    'cosecha_zuniga_qr',
    'cosecha_zuniga_escaneo'
  ]
  LOOP
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'appsheet'
        AND table_name = t
        AND column_name = 'contratista'
    ) THEN
      EXECUTE format(
        'UPDATE %I x
            SET "contratista" = m.id_nuevo
           FROM _mapa_contratistas m
          WHERE x."contratista"::text = m.id_viejo
            AND m.id_viejo <> m.id_nuevo', t);
    END IF;
  END LOOP;
END $$;

DELETE FROM cosecha_zuniga_contratistas c
USING _mapa_contratistas m
WHERE c."id_contratista"::text = m.id_viejo
  AND m.id_viejo <> m.id_nuevo;

-- Misma persona escrita distinto (mayúsculas, punto final, espacios).
CREATE TEMP TABLE _mapa_normalizado ON COMMIT DROP AS
SELECT c."id_contratista"::text AS id_viejo,
       first_value(c."id_contratista"::text) OVER (
         PARTITION BY lower(btrim(c."contratistas", ' .'))
         ORDER BY c."fecha_y_hora" NULLS LAST, c."id_contratista"
       ) AS id_nuevo
FROM cosecha_zuniga_contratistas c
WHERE btrim(c."contratistas", ' .') <> '';

UPDATE cosecha_zuniga_cuadrillas q
   SET "id_contratista" = n.id_nuevo
  FROM _mapa_normalizado n
 WHERE q."id_contratista" = n.id_viejo
   AND n.id_viejo <> n.id_nuevo;

DELETE FROM cosecha_zuniga_contratistas c
USING _mapa_normalizado n
WHERE c."id_contratista"::text = n.id_viejo
  AND n.id_viejo <> n.id_nuevo;

UPDATE cosecha_zuniga_contratistas
   SET "cuadrillas" = NULL
 WHERE "cuadrillas" IS NOT NULL;

ALTER TABLE cosecha_zuniga_contratistas
  ALTER COLUMN "id_contratista" SET NOT NULL;

ALTER TABLE cosecha_zuniga_contratistas
  ALTER COLUMN "contratistas" SET NOT NULL;

ALTER TABLE cosecha_zuniga_contratistas
  ALTER COLUMN "fecha_y_hora" SET DEFAULT now();

UPDATE cosecha_zuniga_contratistas
   SET "fecha_y_hora" = now()
 WHERE "fecha_y_hora" IS NULL;

ALTER TABLE cosecha_zuniga_contratistas
  ALTER COLUMN "fecha_y_hora" SET NOT NULL;

UPDATE cosecha_zuniga_cuadrillas
   SET "fecha_y_hora" = now()
 WHERE "fecha_y_hora" IS NULL;

ALTER TABLE cosecha_zuniga_cuadrillas
  ALTER COLUMN "fecha_y_hora" SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_contratistas_pkey'
  ) THEN
    ALTER TABLE cosecha_zuniga_contratistas
      ADD CONSTRAINT cosecha_zuniga_contratistas_pkey
      PRIMARY KEY ("id_contratista");
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_contratistas_nombre_chk'
  ) THEN
    ALTER TABLE cosecha_zuniga_contratistas
      ADD CONSTRAINT cosecha_zuniga_contratistas_nombre_chk
      CHECK (btrim("contratistas") <> '');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_cuadrillas_contratista_fk'
  ) THEN
    ALTER TABLE cosecha_zuniga_cuadrillas
      ADD CONSTRAINT cosecha_zuniga_cuadrillas_contratista_fk
      FOREIGN KEY ("id_contratista")
      REFERENCES cosecha_zuniga_contratistas ("id_contratista")
      ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cosecha_zuniga_cuadrillas_numero_chk'
  ) THEN
    ALTER TABLE cosecha_zuniga_cuadrillas
      ADD CONSTRAINT cosecha_zuniga_cuadrillas_numero_chk
      CHECK ("cuadrilla" > 0);
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS cosecha_zuniga_contratistas_nombre_norm_uq
  ON cosecha_zuniga_contratistas (lower(btrim("contratistas", ' .')));

CREATE UNIQUE INDEX IF NOT EXISTS cosecha_zuniga_cuadrillas_contratista_numero_uq
  ON cosecha_zuniga_cuadrillas ("id_contratista", "cuadrilla");

DROP INDEX IF EXISTS cosecha_zuniga_cuadrillas_contratista_idx;

CREATE INDEX IF NOT EXISTS cosecha_zuniga_cuadrillas_numero_idx
  ON cosecha_zuniga_cuadrillas ("cuadrilla");

COMMENT ON TABLE cosecha_zuniga_contratistas IS
  'Un contratista por nombre. Las cuadrillas están en cosecha_zuniga_cuadrillas.';

COMMENT ON COLUMN cosecha_zuniga_contratistas."cuadrillas" IS
  'Obsoleta. El número está en cosecha_zuniga_cuadrillas.cuadrilla. Se conserva para AppSheet y debe quedar NULL.';

COMMENT ON COLUMN cosecha_zuniga_contratistas."comentario" IS
  'Nota del contratista, no de una cuadrilla.';

COMMENT ON TABLE cosecha_zuniga_cuadrillas IS
  'Cuadrillas de un contratista. id_cuadrilla reutiliza el id original de contratistas.';

COMMENT ON COLUMN cosecha_zuniga_cuadrillas."cuadrilla" IS
  'Número de cuadrilla, único dentro del contratista. Puede repetirse en otro contratista.';

DO $$
DECLARE
  nombres int;
  huerfanas int;
  padre_con_numero int;
BEGIN
  SELECT count(*) INTO nombres
  FROM (
    SELECT lower(btrim("contratistas", ' .'))
    FROM cosecha_zuniga_contratistas
    GROUP BY 1
    HAVING count(*) > 1
  ) d;

  SELECT count(*) INTO huerfanas
  FROM cosecha_zuniga_cuadrillas q
  WHERE NOT EXISTS (
    SELECT 1 FROM cosecha_zuniga_contratistas c
    WHERE c."id_contratista" = q."id_contratista"
  );

  SELECT count(*) INTO padre_con_numero
  FROM cosecha_zuniga_contratistas
  WHERE "cuadrillas" IS NOT NULL;

  IF nombres > 0 OR huerfanas > 0 OR padre_con_numero > 0 THEN
    RAISE EXCEPTION
      'control zúñiga cuadrillas: nombres=% huerfanas=% padre_con_numero=%',
      nombres, huerfanas, padre_con_numero;
  END IF;
END $$;

COMMIT;
