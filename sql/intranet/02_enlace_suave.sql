-- Enlace suave hacia intranet.contratistas.
--
-- Sin FOREIGN KEY. Borrar un maestro pone el enlace en NULL y deja la fila
-- de tarjas o de cosecha como estaba. Los contratistas nuevos de AppSheet
-- quedan en NULL hasta que alguien los relacione.

ALTER TABLE appsheet.tarjas_contratistas
  DROP CONSTRAINT IF EXISTS tarjas_contratistas_id_intranet_fk;

ALTER TABLE appsheet.cosecha_zuniga_contratistas
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_contratistas_id_intranet_fk;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'appsheet' AND table_name = 'tarjas_contratistas'
      AND column_name = 'id_intranet'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'appsheet' AND table_name = 'tarjas_contratistas'
      AND column_name = 'id_intranet_contratistas'
  ) THEN
    ALTER TABLE appsheet.tarjas_contratistas
      RENAME COLUMN id_intranet TO id_intranet_contratistas;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'appsheet' AND table_name = 'cosecha_zuniga_contratistas'
      AND column_name = 'id_intranet'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'appsheet' AND table_name = 'cosecha_zuniga_contratistas'
      AND column_name = 'id_intranet_contratistas'
  ) THEN
    ALTER TABLE appsheet.cosecha_zuniga_contratistas
      RENAME COLUMN id_intranet TO id_intranet_contratistas;
  END IF;
END $$;

COMMENT ON COLUMN appsheet.tarjas_contratistas.id_intranet_contratistas IS
  'Texto nullable hacia intranet.contratistas.id_intranet. Sin FK. NULL si no hay enlace.';

COMMENT ON COLUMN appsheet.cosecha_zuniga_contratistas.id_intranet_contratistas IS
  'Texto nullable hacia intranet.contratistas.id_intranet. Sin FK. NULL si no hay enlace.';

CREATE OR REPLACE FUNCTION intranet.liberar_enlace_contratista()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = intranet, appsheet, public
AS $$
BEGIN
  UPDATE tarjas_contratistas
  SET id_intranet_contratistas = NULL
  WHERE id_intranet_contratistas = OLD.id_intranet;

  UPDATE cosecha_zuniga_contratistas
  SET id_intranet_contratistas = NULL
  WHERE id_intranet_contratistas = OLD.id_intranet;

  RETURN OLD;
END $$;

DROP TRIGGER IF EXISTS trg_liberar_enlace_contratista ON intranet.contratistas;
CREATE TRIGGER trg_liberar_enlace_contratista
  BEFORE DELETE ON intranet.contratistas
  FOR EACH ROW
  EXECUTE FUNCTION intranet.liberar_enlace_contratista();

-- Solo llena enlaces vacíos, y solo cuando hay un único maestro.
UPDATE appsheet.tarjas_contratistas t
SET id_intranet_contratistas = m.id_intranet
FROM (
  SELECT t2.id_contratista, min(c.id_intranet) AS id_intranet
  FROM appsheet.tarjas_contratistas t2
  JOIN intranet.contratistas c
    ON lower(unaccent(btrim(t2.nombre))) = lower(unaccent(btrim(c.nombre)))
    OR (
      COALESCE(btrim(c.nombre_corto), '') <> ''
      AND lower(unaccent(btrim(t2.nombre))) = lower(unaccent(btrim(c.nombre_corto)))
    )
  GROUP BY t2.id_contratista
  HAVING COUNT(DISTINCT c.id_intranet) = 1
) m
WHERE t.id_contratista = m.id_contratista
  AND t.id_intranet_contratistas IS NULL;

UPDATE appsheet.cosecha_zuniga_contratistas z
SET id_intranet_contratistas = m.id_intranet
FROM (
  SELECT z2.id_contratista, min(c.id_intranet) AS id_intranet
  FROM appsheet.cosecha_zuniga_contratistas z2
  JOIN intranet.contratistas c
    ON lower(unaccent(btrim(z2.contratistas))) = lower(unaccent(btrim(c.nombre)))
    OR (
      COALESCE(btrim(c.nombre_corto), '') <> ''
      AND lower(unaccent(btrim(z2.contratistas))) = lower(unaccent(btrim(c.nombre_corto)))
    )
  GROUP BY z2.id_contratista
  HAVING COUNT(DISTINCT c.id_intranet) = 1
) m
WHERE z.id_contratista = m.id_contratista
  AND z.id_intranet_contratistas IS NULL;
