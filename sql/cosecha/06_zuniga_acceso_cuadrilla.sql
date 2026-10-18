-- =============================================================================
-- Cosecha Zúñiga: cuadrillas por contratista + acceso por cuadrilla
--
-- Correr ANTES de los cambios en AppSheet.
--
-- Vale para cualquier contratista. La app puede guardar de dos formas:
--   1) la lista EnumList del contratista ("1 , 2 , 3")
--   2) el padre y después la cuadrilla hija (y sus cuarteles)
-- En las dos se crea el acceso: usuario = número, clave de 4 dígitos.
--
-- El número de cuadrilla es único en toda la empresa. Si se quita de la
-- lista, la cuadrilla queda libre (id_contratista NULL) y su acceso inactivo.
-- Por eso id_contratista acepta NULL y la FK ya no borra en cascada: el
-- trigger AFTER es el que libera las filas antes del chequeo de la FK.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM cosecha_zuniga_cuadrillas
    GROUP BY cuadrilla
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION
      'hay números de cuadrilla repetidos; corrígelos antes de seguir';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS bk_20261013_contratistas AS
SELECT * FROM cosecha_zuniga_contratistas;

CREATE TABLE IF NOT EXISTS bk_20261013_cuadrillas AS
SELECT * FROM cosecha_zuniga_cuadrillas;

CREATE TABLE IF NOT EXISTS bk_20261013_usuarios AS
SELECT * FROM cosecha_zuniga_usuarios;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'appsheet'
      AND table_name = 'cosecha_zuniga_contratistas'
      AND column_name = 'cuadrillas'
      AND udt_name <> 'text'
  ) THEN
    ALTER TABLE cosecha_zuniga_contratistas
      ALTER COLUMN cuadrillas TYPE text USING cuadrillas::text;
  END IF;
END $$;

UPDATE cosecha_zuniga_contratistas ct
SET cuadrillas = sub.lista
FROM (
  SELECT id_contratista,
         string_agg(cuadrilla::numeric::bigint::text, ' , ' ORDER BY cuadrilla::numeric) AS lista
  FROM cosecha_zuniga_cuadrillas
  WHERE id_contratista IS NOT NULL
  GROUP BY id_contratista
) sub
WHERE sub.id_contratista = ct.id_contratista;

ALTER TABLE cosecha_zuniga_cuadrillas
  ALTER COLUMN id_contratista DROP NOT NULL;

ALTER TABLE cosecha_zuniga_cuadrillas
  DROP CONSTRAINT cosecha_zuniga_cuadrillas_contratista_fk;

ALTER TABLE cosecha_zuniga_cuadrillas
  ADD CONSTRAINT cosecha_zuniga_cuadrillas_contratista_fk
  FOREIGN KEY (id_contratista)
  REFERENCES cosecha_zuniga_contratistas (id_contratista);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cuadrillas_numero
  ON cosecha_zuniga_cuadrillas ((cuadrilla::numeric));

CREATE OR REPLACE FUNCTION cosecha_clave_4d() RETURNS text
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE c text;
BEGIN
  LOOP
    c := lpad((floor(random() * 10000))::int::text, 4, '0');
    EXIT WHEN c NOT IN ('0000', '1234', '4321')
          AND c !~ '^(\d)\1{3}$';
  END LOOP;
  RETURN c;
END $$;

CREATE OR REPLACE FUNCTION cosecha_sync_cuadrillas_contratista()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_num      bigint;
  v_cuad     record;
  v_nums     bigint[];
  v_id_cuad  text;
BEGIN
  -- La cuadrilla hija refresca esta lista. No volver a sincronizar.
  IF current_setting('cosecha.syncing', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
  END IF;

  PERFORM set_config('cosecha.syncing', '1', true);

  IF TG_OP = 'DELETE' THEN
    UPDATE cosecha_zuniga_usuarios u SET activo = false
    FROM cosecha_zuniga_cuadrillas c
    WHERE u.id_cuadrilla = c.id_cuadrilla
      AND c.id_contratista = OLD.id_contratista;

    UPDATE cosecha_zuniga_cuadrillas
    SET id_contratista = NULL
    WHERE id_contratista = OLD.id_contratista;

    PERFORM set_config('cosecha.syncing', '0', true);
    RETURN OLD;
  END IF;

  SELECT COALESCE(array_agg(DISTINCT x::bigint), '{}')
  INTO v_nums
  FROM regexp_split_to_table(COALESCE(NEW.cuadrillas, ''), '\s*,\s*') AS x
  WHERE x ~ '^\d+$';

  FOREACH v_num IN ARRAY v_nums LOOP
    SELECT * INTO v_cuad
    FROM cosecha_zuniga_cuadrillas
    WHERE cuadrilla::numeric = v_num;

    IF FOUND THEN
      IF v_cuad.id_contratista IS NOT NULL
         AND v_cuad.id_contratista <> NEW.id_contratista THEN
        RAISE EXCEPTION 'La cuadrilla % ya pertenece a otro contratista', v_num;
      END IF;

      UPDATE cosecha_zuniga_cuadrillas
      SET id_contratista = NEW.id_contratista
      WHERE id_cuadrilla = v_cuad.id_cuadrilla;

      v_id_cuad := v_cuad.id_cuadrilla;
    ELSE
      v_id_cuad := substr(md5(random()::text || clock_timestamp()::text), 1, 8);
      INSERT INTO cosecha_zuniga_cuadrillas
        (id_cuadrilla, id_contratista, cuadrilla, fecha_y_hora)
      VALUES (v_id_cuad, NEW.id_contratista, v_num, now());
    END IF;

    IF EXISTS (
      SELECT 1 FROM cosecha_zuniga_usuarios WHERE id_cuadrilla = v_id_cuad
    ) THEN
      UPDATE cosecha_zuniga_usuarios
      SET activo = true, usuario = v_num::text, rol = 'cuadrilla'
      WHERE id_cuadrilla = v_id_cuad;
    ELSE
      INSERT INTO cosecha_zuniga_usuarios
        (usuarioid, usuario, "contraseña", rol, id_cuadrilla, activo, creado_en)
      VALUES
        (substr(md5(random()::text || clock_timestamp()::text), 1, 8),
         v_num::text, cosecha_clave_4d(), 'cuadrilla', v_id_cuad, true, now());
    END IF;
  END LOOP;

  UPDATE cosecha_zuniga_usuarios u SET activo = false
  FROM cosecha_zuniga_cuadrillas c
  WHERE u.id_cuadrilla = c.id_cuadrilla
    AND c.id_contratista = NEW.id_contratista
    AND NOT (c.cuadrilla::numeric = ANY (v_nums::numeric[]));

  UPDATE cosecha_zuniga_cuadrillas c
  SET id_contratista = NULL
  WHERE c.id_contratista = NEW.id_contratista
    AND NOT (c.cuadrilla::numeric = ANY (v_nums::numeric[]));

  PERFORM set_config('cosecha.syncing', '0', true);
  RETURN NEW;
EXCEPTION
  WHEN OTHERS THEN
    PERFORM set_config('cosecha.syncing', '0', true);
    RAISE;
END $$;

-- La app guarda el padre y después la fila hija. Ahí también nace el acceso,
-- y la lista del contratista queda igual a sus cuadrillas.
CREATE OR REPLACE FUNCTION cosecha_refresca_lista_contratista(p_id text)
RETURNS void
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_lista text;
BEGIN
  IF p_id IS NULL THEN
    RETURN;
  END IF;

  SELECT string_agg(cuadrilla::text, ' , ' ORDER BY cuadrilla)
  INTO v_lista
  FROM cosecha_zuniga_cuadrillas
  WHERE id_contratista = p_id;

  PERFORM set_config('cosecha.syncing', '1', true);
  UPDATE cosecha_zuniga_contratistas
  SET cuadrillas = v_lista
  WHERE id_contratista = p_id
    AND cuadrillas IS DISTINCT FROM v_lista;
  PERFORM set_config('cosecha.syncing', '0', true);
END $$;

CREATE OR REPLACE FUNCTION cosecha_sync_desde_cuadrilla()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_otra record;
BEGIN
  IF current_setting('cosecha.syncing', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
  END IF;

  IF TG_OP = 'DELETE' THEN
    PERFORM cosecha_refresca_lista_contratista(OLD.id_contratista);
    RETURN OLD;
  END IF;

  SELECT id_cuadrilla, id_contratista
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

  IF EXISTS (
    SELECT 1 FROM cosecha_zuniga_usuarios WHERE id_cuadrilla = NEW.id_cuadrilla
  ) THEN
    UPDATE cosecha_zuniga_usuarios
    SET activo = (NEW.id_contratista IS NOT NULL),
        usuario = NEW.cuadrilla::text,
        rol = 'cuadrilla'
    WHERE id_cuadrilla = NEW.id_cuadrilla;
  ELSE
    INSERT INTO cosecha_zuniga_usuarios
      (usuarioid, usuario, "contraseña", rol, id_cuadrilla, activo, creado_en)
    VALUES
      (substr(md5(random()::text || clock_timestamp()::text), 1, 8),
       NEW.cuadrilla::text, cosecha_clave_4d(), 'cuadrilla', NEW.id_cuadrilla,
       (NEW.id_contratista IS NOT NULL), now());
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.id_contratista IS DISTINCT FROM NEW.id_contratista THEN
    PERFORM cosecha_refresca_lista_contratista(OLD.id_contratista);
  END IF;
  PERFORM cosecha_refresca_lista_contratista(NEW.id_contratista);

  RETURN NEW;
END $$;

-- 08_zuniga_max_cuadrillas.sql vuelve a crear esta función y le agrega el tope.
CREATE OR REPLACE FUNCTION cosecha_valida_numero_cuadrilla()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_otra record;
BEGIN
  IF current_setting('cosecha.syncing', true) = '1' THEN
    RETURN NEW;
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

CREATE OR REPLACE FUNCTION cosecha_normaliza_lista_cuadrillas()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
BEGIN
  SELECT string_agg(n::text, ' , ' ORDER BY n)
  INTO NEW.cuadrillas
  FROM (
    SELECT DISTINCT x::bigint AS n
    FROM regexp_split_to_table(COALESCE(NEW.cuadrillas, ''), '\s*,\s*') AS x
    WHERE x ~ '^\d+$'
  ) s;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_contratistas_normaliza ON cosecha_zuniga_contratistas;
CREATE TRIGGER trg_contratistas_normaliza
  BEFORE INSERT OR UPDATE OF cuadrillas ON cosecha_zuniga_contratistas
  FOR EACH ROW EXECUTE FUNCTION cosecha_normaliza_lista_cuadrillas();

-- AFTER en el alta: la fila del contratista ya existe cuando se crean las hijas.
-- BEFORE en el delete: hay que soltar las cuadrillas antes del chequeo de la FK.
-- Un AFTER DELETE llega tarde; la FK interna dispara primero y aborta el borrado.
DROP TRIGGER IF EXISTS trg_contratistas_sync_cuadrillas ON cosecha_zuniga_contratistas;
CREATE TRIGGER trg_contratistas_sync_cuadrillas
  AFTER INSERT OR UPDATE OF cuadrillas ON cosecha_zuniga_contratistas
  FOR EACH ROW EXECUTE FUNCTION cosecha_sync_cuadrillas_contratista();

DROP TRIGGER IF EXISTS trg_contratistas_libera_cuadrillas ON cosecha_zuniga_contratistas;
CREATE TRIGGER trg_contratistas_libera_cuadrillas
  BEFORE DELETE ON cosecha_zuniga_contratistas
  FOR EACH ROW EXECUTE FUNCTION cosecha_sync_cuadrillas_contratista();

DROP TRIGGER IF EXISTS trg_cuadrillas_sync_acceso ON cosecha_zuniga_cuadrillas;
CREATE TRIGGER trg_cuadrillas_sync_acceso
  AFTER INSERT OR UPDATE OF cuadrilla, id_contratista OR DELETE
  ON cosecha_zuniga_cuadrillas
  FOR EACH ROW EXECUTE FUNCTION cosecha_sync_desde_cuadrilla();

DROP TRIGGER IF EXISTS trg_cuadrillas_valida_numero ON cosecha_zuniga_cuadrillas;
CREATE TRIGGER trg_cuadrillas_valida_numero
  BEFORE INSERT OR UPDATE OF cuadrilla, id_contratista
  ON cosecha_zuniga_cuadrillas
  FOR EACH ROW EXECUTE FUNCTION cosecha_valida_numero_cuadrilla();

UPDATE cosecha_zuniga_usuarios u
SET usuario = c.cuadrilla::numeric::bigint::text,
    rol = 'cuadrilla'
FROM cosecha_zuniga_cuadrillas c
WHERE u.id_cuadrilla = c.id_cuadrilla;

UPDATE cosecha_zuniga_usuarios
SET "contraseña" = cosecha_clave_4d()
WHERE rol = 'cuadrilla'
  AND ("contraseña" IS NULL OR "contraseña" IN ('', '1234'));

INSERT INTO cosecha_zuniga_usuarios
  (usuarioid, usuario, "contraseña", rol, id_cuadrilla, activo, creado_en)
SELECT substr(md5(random()::text || c.id_cuadrilla), 1, 8),
       c.cuadrilla::numeric::bigint::text,
       cosecha_clave_4d(),
       'cuadrilla',
       c.id_cuadrilla,
       (c.id_contratista IS NOT NULL),
       now()
FROM cosecha_zuniga_cuadrillas c
WHERE NOT EXISTS (
  SELECT 1 FROM cosecha_zuniga_usuarios u
  WHERE u.id_cuadrilla = c.id_cuadrilla
);

COMMENT ON COLUMN cosecha_zuniga_contratistas.cuadrillas IS
  'EnumList AppSheet ("1 , 2 , 3"). El trigger sincroniza cuadrillas y el acceso de cada número.';

COMMENT ON COLUMN cosecha_zuniga_cuadrillas.cuadrilla IS
  'Número de cuadrilla, único en toda la empresa.';

COMMENT ON COLUMN cosecha_zuniga_cuadrillas.id_contratista IS
  'NULL si la cuadrilla no está asignada. El trigger la libera al quitarla de la lista.';

COMMIT;
