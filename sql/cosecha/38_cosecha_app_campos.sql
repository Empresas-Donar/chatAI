-- =============================================================================
-- Cosecha app: campos
--
-- Un campo (Isla de Maipo, Talagante, …) agrupa contratistas, cuadrillas,
-- cuarteles, usuarios, tratos, bins, QR, escaneos, registros y salidas.
-- La cuadrilla 1 de Isla y la cuadrilla 1 de Talagante son filas distintas.
-- El usuario que se escribe sigue siendo el número. El login de AppSheet
-- es codigo || '-' || usuario: isla-1, talagante-1, isla-admin.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE TABLE cosecha_app_campos (
  id_campo     text PRIMARY KEY,
  nombre_campo text NOT NULL,
  codigo       text NOT NULL,
  CONSTRAINT cosecha_app_campos_nombre_chk CHECK (btrim(nombre_campo) <> ''),
  CONSTRAINT cosecha_app_campos_codigo_chk CHECK (codigo ~ '^[a-z0-9]+(-[a-z0-9]+)*$')
);

CREATE UNIQUE INDEX cosecha_app_campos_nombre_uq
  ON cosecha_app_campos (lower(btrim(nombre_campo)));

CREATE UNIQUE INDEX cosecha_app_campos_codigo_uq
  ON cosecha_app_campos (codigo);

COMMENT ON TABLE cosecha_app_campos IS
  'Predio de la app. Isla de Maipo y Talagante son filas de aquí.';

COMMENT ON COLUMN cosecha_app_campos.codigo IS
  'Prefijo del login. isla-1 es la cuadrilla 1 de Isla de Maipo.';

INSERT INTO cosecha_app_campos (id_campo, nombre_campo, codigo) VALUES
  ('isla-de-maipo', 'Isla de Maipo', 'isla'),
  ('talagante', 'Talagante', 'talagante');

ALTER TABLE cosecha_app_contratistas      ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_cuadrillas        ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_cuarteles         ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_usuarios          ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_usuarios          ADD COLUMN login text;
ALTER TABLE cosecha_app_tratos            ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_qr                ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_bins              ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_escaneo           ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_registro          ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_salidas_lote      ADD COLUMN id_campo text;
ALTER TABLE cosecha_app_salidas_trabajador ADD COLUMN id_campo text;

UPDATE cosecha_app_cuarteles
SET id_campo = 'isla-de-maipo';

UPDATE cosecha_app_usuarios
SET id_campo = 'isla-de-maipo'
WHERE id_campo IS NULL;

-- ---------------------------------------------------------------------------
-- El campo manda. Si la fila trae otro, se rechaza.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION cosecha_app_usuario_login()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_campo text;
  v_codigo text;
BEGIN
  IF NEW.id_cuadrilla IS NOT NULL THEN
    SELECT id_campo INTO v_campo
    FROM cosecha_app_cuadrillas
    WHERE id_cuadrilla = NEW.id_cuadrilla;

    IF v_campo IS NULL THEN
      RAISE EXCEPTION 'La cuadrilla % no existe', NEW.id_cuadrilla;
    END IF;

    IF NEW.id_campo IS NULL THEN
      NEW.id_campo := v_campo;
    ELSIF NEW.id_campo IS DISTINCT FROM v_campo THEN
      RAISE EXCEPTION 'El usuario y la cuadrilla son de campos distintos';
    END IF;
  END IF;

  IF NEW.id_campo IS NULL THEN
    RAISE EXCEPTION 'El usuario no tiene campo';
  END IF;

  SELECT codigo INTO v_codigo
  FROM cosecha_app_campos
  WHERE id_campo = NEW.id_campo;

  IF v_codigo IS NULL THEN
    RAISE EXCEPTION 'El campo % no existe', NEW.id_campo;
  END IF;

  NEW.login := v_codigo || '-' || lower(btrim(NEW.usuario));
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_campo_refresca_login()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
BEGIN
  IF NEW.codigo IS DISTINCT FROM OLD.codigo THEN
    UPDATE cosecha_app_usuarios
    SET usuario = usuario
    WHERE id_campo = NEW.id_campo;
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_qr_campo()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_campo text;
BEGIN
  SELECT id_campo INTO v_campo
  FROM cosecha_app_cuadrillas
  WHERE id_cuadrilla = NEW.id_cuadrilla;

  IF v_campo IS NULL THEN
    RAISE EXCEPTION 'La cuadrilla del QR no existe';
  END IF;

  IF NEW.id_campo IS NULL THEN
    NEW.id_campo := v_campo;
  ELSIF NEW.id_campo IS DISTINCT FROM v_campo THEN
    RAISE EXCEPTION 'El QR y la cuadrilla son de campos distintos';
  END IF;

  IF NEW.id_contratista IS NOT NULL AND EXISTS (
    SELECT 1 FROM cosecha_app_contratistas
    WHERE id_contratista = NEW.id_contratista
      AND id_campo IS DISTINCT FROM NEW.id_campo
  ) THEN
    RAISE EXCEPTION 'El QR y el contratista son de campos distintos';
  END IF;

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_salida_lote_campo()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_campo text;
BEGIN
  SELECT id_campo INTO v_campo
  FROM cosecha_app_cuadrillas
  WHERE id_cuadrilla = NEW.id_cuadrilla;

  IF v_campo IS NULL THEN
    RAISE EXCEPTION 'La cuadrilla de la salida no existe';
  END IF;

  IF NEW.id_campo IS NULL THEN
    NEW.id_campo := v_campo;
  ELSIF NEW.id_campo IS DISTINCT FROM v_campo THEN
    RAISE EXCEPTION 'La salida y la cuadrilla son de campos distintos';
  END IF;

  IF NEW.id_registro IS NOT NULL AND EXISTS (
    SELECT 1 FROM cosecha_app_registro
    WHERE id_registro = NEW.id_registro
      AND id_campo IS DISTINCT FROM NEW.id_campo
  ) THEN
    RAISE EXCEPTION 'La salida y el registro son de campos distintos';
  END IF;

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_salida_trabajador_campo()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_campo text;
BEGIN
  IF NEW.id_campo IS NULL AND NEW.id_qr IS NOT NULL THEN
    SELECT id_campo INTO v_campo
    FROM cosecha_app_qr
    WHERE id_qr = NEW.id_qr;
    NEW.id_campo := v_campo;
  END IF;

  IF NEW.id_campo IS NULL THEN
    RAISE EXCEPTION 'La salida del trabajador no tiene campo';
  END IF;

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_trato_cuartel_campo()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_trato text;
  v_cuartel text;
BEGIN
  SELECT id_campo INTO v_trato
  FROM cosecha_app_tratos WHERE id_trato = NEW.id_trato;

  SELECT id_campo INTO v_cuartel
  FROM cosecha_app_cuarteles WHERE id_cuartel = NEW.id_cuartel;

  IF v_trato IS NULL OR v_cuartel IS NULL OR v_trato IS DISTINCT FROM v_cuartel THEN
    RAISE EXCEPTION 'El trato y el cuartel son de campos distintos';
  END IF;

  RETURN NEW;
END $$;

CREATE TRIGGER trg_usuario_login
  BEFORE INSERT OR UPDATE OF usuario, id_campo, id_cuadrilla
  ON cosecha_app_usuarios
  FOR EACH ROW EXECUTE FUNCTION cosecha_app_usuario_login();

CREATE TRIGGER trg_campo_refresca_login
  AFTER UPDATE OF codigo ON cosecha_app_campos
  FOR EACH ROW EXECUTE FUNCTION cosecha_app_campo_refresca_login();

CREATE TRIGGER trg_qr_campo
  BEFORE INSERT OR UPDATE OF id_cuadrilla, id_contratista, id_campo
  ON cosecha_app_qr
  FOR EACH ROW EXECUTE FUNCTION cosecha_app_qr_campo();

CREATE TRIGGER trg_salidas_lote_campo
  BEFORE INSERT OR UPDATE OF id_cuadrilla, id_registro, id_campo
  ON cosecha_app_salidas_lote
  FOR EACH ROW EXECUTE FUNCTION cosecha_app_salida_lote_campo();

CREATE TRIGGER trg_salidas_trabajador_campo
  BEFORE INSERT OR UPDATE OF id_qr, id_campo
  ON cosecha_app_salidas_trabajador
  FOR EACH ROW EXECUTE FUNCTION cosecha_app_salida_trabajador_campo();

CREATE TRIGGER trg_trato_cuartel_campo
  BEFORE INSERT OR UPDATE OF id_trato, id_cuartel
  ON cosecha_app_tratos_cuarteles
  FOR EACH ROW EXECUTE FUNCTION cosecha_app_trato_cuartel_campo();

-- El admin ya existe: el trigger le arma el login.
UPDATE cosecha_app_usuarios
SET usuario = usuario
WHERE id_campo IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Cuadrillas y accesos, acotados al campo del contratista.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION cosecha_app_valida_numero_cuadrilla()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_otra record;
  v_max int;
BEGIN
  IF current_setting('cosecha_app.syncing', true) = '1' THEN
    RETURN NEW;
  END IF;

  IF NEW.id_campo IS NULL THEN
    RAISE EXCEPTION 'La cuadrilla no tiene campo';
  END IF;

  v_max := cosecha_app_max_cuadrillas();

  IF NEW.cuadrilla < 1 OR NEW.cuadrilla > v_max THEN
    RAISE EXCEPTION 'La cuadrilla % supera el máximo permitido (%)', NEW.cuadrilla, v_max;
  END IF;

  IF NEW.id_contratista IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM cosecha_app_contratistas
    WHERE id_contratista = NEW.id_contratista
      AND id_campo = NEW.id_campo
  ) THEN
    RAISE EXCEPTION 'El contratista no es de este campo';
  END IF;

  SELECT id_contratista
  INTO v_otra
  FROM cosecha_app_cuadrillas
  WHERE cuadrilla = NEW.cuadrilla
    AND id_campo = NEW.id_campo
    AND id_cuadrilla <> NEW.id_cuadrilla;

  IF FOUND THEN
    IF v_otra.id_contratista IS NULL THEN
      RAISE EXCEPTION
        'La cuadrilla % está libre en este campo. Reasígnela en vez de crear otra',
        NEW.cuadrilla;
    END IF;
    RAISE EXCEPTION 'La cuadrilla % ya pertenece a otro contratista de este campo', NEW.cuadrilla;
  END IF;

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_sync_cuadrillas_contratista()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_num      bigint;
  v_cuad     record;
  v_nums     bigint[];
  v_id_cuad  text;
BEGIN
  IF current_setting('cosecha_app.syncing', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
  END IF;

  IF TG_OP <> 'DELETE' AND NEW.id_campo IS NULL THEN
    RAISE EXCEPTION 'El contratista no tiene campo';
  END IF;

  PERFORM set_config('cosecha_app.syncing', '1', true);

  IF TG_OP = 'DELETE' THEN
    UPDATE cosecha_app_usuarios u SET activo = false
    FROM cosecha_app_cuadrillas c
    WHERE u.id_cuadrilla = c.id_cuadrilla
      AND c.id_contratista = OLD.id_contratista;

    UPDATE cosecha_app_cuadrillas
    SET id_contratista = NULL
    WHERE id_contratista = OLD.id_contratista;

    PERFORM set_config('cosecha_app.syncing', '0', true);
    RETURN OLD;
  END IF;

  SELECT COALESCE(array_agg(DISTINCT x::bigint), '{}')
  INTO v_nums
  FROM regexp_split_to_table(COALESCE(NEW.cuadrillas, ''), '\s*,\s*') AS x
  WHERE x ~ '^\d+$';

  FOREACH v_num IN ARRAY v_nums LOOP
    SELECT * INTO v_cuad
    FROM cosecha_app_cuadrillas
    WHERE cuadrilla::numeric = v_num
      AND id_campo = NEW.id_campo;

    IF FOUND THEN
      IF v_cuad.id_contratista IS NOT NULL
         AND v_cuad.id_contratista <> NEW.id_contratista THEN
        RAISE EXCEPTION 'La cuadrilla % ya pertenece a otro contratista de este campo', v_num;
      END IF;

      UPDATE cosecha_app_cuadrillas
      SET id_contratista = NEW.id_contratista
      WHERE id_cuadrilla = v_cuad.id_cuadrilla;

      v_id_cuad := v_cuad.id_cuadrilla;
    ELSE
      v_id_cuad := substr(md5(random()::text || clock_timestamp()::text), 1, 8);
      INSERT INTO cosecha_app_cuadrillas
        (id_cuadrilla, id_contratista, cuadrilla, fecha_y_hora, id_campo)
      VALUES (v_id_cuad, NEW.id_contratista, v_num, now(), NEW.id_campo);
    END IF;

    IF EXISTS (
      SELECT 1 FROM cosecha_app_usuarios WHERE id_cuadrilla = v_id_cuad
    ) THEN
      UPDATE cosecha_app_usuarios
      SET activo = true,
          usuario = v_num::text,
          rol = 'cuadrilla',
          id_campo = NEW.id_campo
      WHERE id_cuadrilla = v_id_cuad;
    ELSE
      INSERT INTO cosecha_app_usuarios
        (usuarioid, usuario, "contraseña", rol, id_cuadrilla, id_campo, activo, creado_en)
      VALUES
        (substr(md5(random()::text || clock_timestamp()::text), 1, 8),
         v_num::text, cosecha_clave_4d(), 'cuadrilla', v_id_cuad, NEW.id_campo, true, now());
    END IF;
  END LOOP;

  UPDATE cosecha_app_usuarios u SET activo = false
  FROM cosecha_app_cuadrillas c
  WHERE u.id_cuadrilla = c.id_cuadrilla
    AND c.id_contratista = NEW.id_contratista
    AND NOT (c.cuadrilla::numeric = ANY (v_nums::numeric[]));

  UPDATE cosecha_app_cuadrillas c
  SET id_contratista = NULL
  WHERE c.id_contratista = NEW.id_contratista
    AND NOT (c.cuadrilla::numeric = ANY (v_nums::numeric[]));

  PERFORM set_config('cosecha_app.syncing', '0', true);
  RETURN NEW;
EXCEPTION
  WHEN OTHERS THEN
    PERFORM set_config('cosecha_app.syncing', '0', true);
    RAISE;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_sync_desde_cuadrilla()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_otra record;
BEGIN
  IF current_setting('cosecha_app.syncing', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
  END IF;

  IF TG_OP = 'DELETE' THEN
    PERFORM cosecha_app_refresca_lista_contratista(OLD.id_contratista);
    RETURN OLD;
  END IF;

  SELECT id_cuadrilla, id_contratista
  INTO v_otra
  FROM cosecha_app_cuadrillas
  WHERE cuadrilla = NEW.cuadrilla
    AND id_campo = NEW.id_campo
    AND id_cuadrilla <> NEW.id_cuadrilla;

  IF FOUND THEN
    IF v_otra.id_contratista IS NULL THEN
      RAISE EXCEPTION
        'La cuadrilla % está libre en este campo. Reasígnela en vez de crear otra',
        NEW.cuadrilla;
    END IF;
    RAISE EXCEPTION 'La cuadrilla % ya pertenece a otro contratista de este campo', NEW.cuadrilla;
  END IF;

  IF EXISTS (
    SELECT 1 FROM cosecha_app_usuarios WHERE id_cuadrilla = NEW.id_cuadrilla
  ) THEN
    UPDATE cosecha_app_usuarios
    SET activo = (NEW.id_contratista IS NOT NULL),
        usuario = NEW.cuadrilla::text,
        rol = 'cuadrilla',
        id_campo = NEW.id_campo
    WHERE id_cuadrilla = NEW.id_cuadrilla;
  ELSE
    INSERT INTO cosecha_app_usuarios
      (usuarioid, usuario, "contraseña", rol, id_cuadrilla, id_campo, activo, creado_en)
    VALUES
      (substr(md5(random()::text || clock_timestamp()::text), 1, 8),
       NEW.cuadrilla::text, cosecha_clave_4d(), 'cuadrilla', NEW.id_cuadrilla,
       NEW.id_campo, (NEW.id_contratista IS NOT NULL), now());
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.id_contratista IS DISTINCT FROM NEW.id_contratista THEN
    PERFORM cosecha_app_refresca_lista_contratista(OLD.id_contratista);
  END IF;
  PERFORM cosecha_app_refresca_lista_contratista(NEW.id_contratista);

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_registro_bin()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_trato text;
  v_campo text;
BEGIN
  IF NEW.id_bins IS NULL OR NEW.id_bins = '' THEN
    RAISE EXCEPTION 'El registro no trae id_bins';
  END IF;
  IF NEW.bins IS NULL THEN
    RAISE EXCEPTION 'Falta el código del bin';
  END IF;

  SELECT id_campo INTO v_campo
  FROM cosecha_app_cuarteles
  WHERE id_cuartel = NEW.id_cuartel;

  IF v_campo IS NULL THEN
    RAISE EXCEPTION 'El cuartel % no tiene campo', NEW.id_cuartel;
  END IF;

  IF NEW.id_campo IS NULL THEN
    NEW.id_campo := v_campo;
  ELSIF NEW.id_campo IS DISTINCT FROM v_campo THEN
    RAISE EXCEPTION 'El registro y el cuartel son de campos distintos';
  END IF;

  IF NEW.id_cuadrilla IS NOT NULL AND EXISTS (
    SELECT 1 FROM cosecha_app_cuadrillas
    WHERE id_cuadrilla = NEW.id_cuadrilla
      AND id_campo IS DISTINCT FROM NEW.id_campo
  ) THEN
    RAISE EXCEPTION 'La cuadrilla no es de este campo';
  END IF;

  IF NEW.id_contratista IS NOT NULL AND EXISTS (
    SELECT 1 FROM cosecha_app_contratistas
    WHERE id_contratista = NEW.id_contratista
      AND id_campo IS DISTINCT FROM NEW.id_campo
  ) THEN
    RAISE EXCEPTION 'El contratista no es de este campo';
  END IF;

  v_trato := cosecha_app_trato_para(NEW.id_cuartel, NEW.fecha_y_hora::date);
  IF v_trato IS NULL THEN
    RAISE EXCEPTION
      'No hay trato vigente para el cuartel % al %',
      NEW.id_cuartel, NEW.fecha_y_hora::date;
  END IF;

  IF EXISTS (
    SELECT 1 FROM cosecha_app_tratos
    WHERE id_trato = v_trato
      AND id_campo IS DISTINCT FROM NEW.id_campo
  ) THEN
    RAISE EXCEPTION 'El trato vigente no es de este campo';
  END IF;

  INSERT INTO cosecha_app_bins (id_bins, bins, id_trato, id_campo)
  VALUES (NEW.id_bins, NEW.bins, v_trato, NEW.id_campo)
  ON CONFLICT (id_bins) DO UPDATE
    SET bins = EXCLUDED.bins,
        id_trato = EXCLUDED.id_trato,
        id_campo = EXCLUDED.id_campo;

  IF TG_OP = 'UPDATE' THEN
    UPDATE cosecha_app_escaneo e
    SET id_trato = v_trato,
        id_campo = NEW.id_campo,
        bins = NEW.bins::text,
        precio_trato_aplicado = t.precio_capacho,
        piso_aplicado = t.piso_garantizado_diario
    FROM cosecha_app_tratos t
    WHERE e.id_bins = NEW.id_bins
      AND t.id_trato = v_trato
      AND (
        e.id_trato IS DISTINCT FROM v_trato
        OR e.id_campo IS DISTINCT FROM NEW.id_campo
        OR e.bins IS DISTINCT FROM NEW.bins::text
        OR e.precio_trato_aplicado IS DISTINCT FROM t.precio_capacho
        OR e.piso_aplicado IS DISTINCT FROM t.piso_garantizado_diario
      );
  END IF;

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_escaneo_trato()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  v_campo text;
BEGIN
  IF NEW.id_bins IS NOT NULL AND NEW.id_bins <> '' THEN
    SELECT b.id_trato, b.bins::text, t.precio_capacho, t.piso_garantizado_diario, b.id_campo
      INTO NEW.id_trato, NEW.bins, NEW.precio_trato_aplicado, NEW.piso_aplicado, v_campo
    FROM cosecha_app_bins b
    LEFT JOIN cosecha_app_tratos t ON t.id_trato = b.id_trato
    WHERE b.id_bins = NEW.id_bins;

    IF v_campo IS NOT NULL THEN
      IF NEW.id_campo IS NULL THEN
        NEW.id_campo := v_campo;
      ELSIF NEW.id_campo IS DISTINCT FROM v_campo THEN
        RAISE EXCEPTION 'El escaneo y el bin son de campos distintos';
      END IF;
    END IF;
  END IF;

  IF NEW.id_campo IS NULL AND NEW.id_cuadrilla IS NOT NULL THEN
    SELECT id_campo INTO NEW.id_campo
    FROM cosecha_app_cuadrillas
    WHERE id_cuadrilla = NEW.id_cuadrilla;
  END IF;

  IF NEW.id_cuadrilla IS NOT NULL AND NEW.id_campo IS NOT NULL AND EXISTS (
    SELECT 1 FROM cosecha_app_cuadrillas
    WHERE id_cuadrilla = NEW.id_cuadrilla
      AND id_campo IS DISTINCT FROM NEW.id_campo
  ) THEN
    RAISE EXCEPTION 'La cuadrilla no es del campo del escaneo';
  END IF;

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_app_salidas_lote_expandir()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO appsheet, pg_catalog
AS $$
DECLARE
  k           text;
  v_id_qr     text;
  v_fecha     date;
  v_bins      text;
  v_cuadrilla text;
  e           record;
BEGIN
  SELECT r.id_bins
    INTO v_bins
    FROM cosecha_app_registro r
   WHERE r.id_registro = NEW.id_registro
     AND r.id_campo = NEW.id_campo;

  IF v_bins IS NULL THEN
    RAISE EXCEPTION 'El registro % no tiene bin en este campo', NEW.id_registro;
  END IF;

  SELECT c.cuadrilla::text
    INTO v_cuadrilla
    FROM cosecha_app_cuadrillas c
   WHERE c.id_cuadrilla = NEW.id_cuadrilla
     AND c.id_campo = NEW.id_campo;

  FOREACH k IN ARRAY regexp_split_to_array(trim(NEW.trabajadores), '\s*,\s*')
  LOOP
    CONTINUE WHEN k IS NULL OR btrim(k) = '';
    k := btrim(k);

    IF position('|' IN k) > 0 THEN
      v_id_qr := split_part(k, '|', 3);
    ELSE
      v_id_qr := substring(k FROM position('-' IN k) + 1);
    END IF;

    IF v_id_qr IS NULL OR btrim(v_id_qr) = '' THEN
      RAISE EXCEPTION 'Clave de trabajador inválida: %', k;
    END IF;

    SELECT es.trabajador,
           es.rut_trabajador,
           es.codigo_qr,
           COALESCE(es.fecha, es.fecha_y_hora::date) AS fecha,
           es.fecha_y_hora,
           COALESCE(b.id_trato, es.id_trato) AS id_trato
      INTO e
      FROM cosecha_app_escaneo es
      LEFT JOIN cosecha_app_bins b ON b.id_bins = es.id_bins
     WHERE es.id_registro = NEW.id_registro
       AND es.id_qr = v_id_qr
       AND es.id_campo = NEW.id_campo
     ORDER BY es.fecha_y_hora DESC
     LIMIT 1;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'No hay escaneos de % en el registro %', v_id_qr, NEW.id_registro;
    END IF;

    v_fecha := e.fecha;

    DELETE FROM cosecha_app_salidas_trabajador
     WHERE id_qr = v_id_qr
       AND fecha = v_fecha
       AND id_campo = NEW.id_campo;

    INSERT INTO cosecha_app_salidas_trabajador (
      id_salida, fecha, id_qr, trabajador, rut, codigo_qr, accion_piso,
      comentario, hora_salida, registrado_por, id_bins, id_trato, id_campo, created_at
    ) VALUES (
      'salida-' || NEW.id_campo || '-' || to_char(v_fecha, 'YYYYMMDD') || '-' || v_id_qr,
      v_fecha,
      v_id_qr,
      e.trabajador,
      e.rut_trabajador,
      e.codigo_qr,
      NEW.accion_piso,
      'abandono ' || COALESCE(v_cuadrilla, NEW.id_cuadrilla)
        || COALESCE(' - ' || NULLIF(btrim(NEW.observacion), ''), ''),
      e.fecha_y_hora,
      NEW.registrado_por,
      v_bins,
      e.id_trato,
      NEW.id_campo,
      now()
    );
  END LOOP;

  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------------
-- Obliga el campo y suelta la unicidad global del número de cuadrilla.
-- ---------------------------------------------------------------------------

ALTER TABLE cosecha_app_contratistas       ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_cuadrillas         ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_cuarteles          ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_usuarios           ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_usuarios           ALTER COLUMN login SET NOT NULL;
ALTER TABLE cosecha_app_tratos             ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_qr                 ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_bins               ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_escaneo            ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_registro           ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_salidas_lote       ALTER COLUMN id_campo SET NOT NULL;
ALTER TABLE cosecha_app_salidas_trabajador ALTER COLUMN id_campo SET NOT NULL;

ALTER TABLE cosecha_app_contratistas
  ADD CONSTRAINT cosecha_app_contratistas_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_cuadrillas
  ADD CONSTRAINT cosecha_app_cuadrillas_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_cuarteles
  ADD CONSTRAINT cosecha_app_cuarteles_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_usuarios
  ADD CONSTRAINT cosecha_app_usuarios_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_tratos
  ADD CONSTRAINT cosecha_app_tratos_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_qr
  ADD CONSTRAINT cosecha_app_qr_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_bins
  ADD CONSTRAINT cosecha_app_bins_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_escaneo
  ADD CONSTRAINT cosecha_app_escaneo_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_registro
  ADD CONSTRAINT cosecha_app_registro_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_salidas_lote
  ADD CONSTRAINT cosecha_app_salidas_lote_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

ALTER TABLE cosecha_app_salidas_trabajador
  ADD CONSTRAINT cosecha_app_salidas_trabajador_campo_fk
  FOREIGN KEY (id_campo) REFERENCES cosecha_app_campos (id_campo);

DROP INDEX IF EXISTS cosecha_app_cuadrillas_numero_uq;
DROP INDEX IF EXISTS cosecha_app_usuarios_usuario_uq;
DROP INDEX IF EXISTS cosecha_app_contratistas_nombre_norm_uq;

CREATE UNIQUE INDEX cosecha_app_cuadrillas_campo_numero_uq
  ON cosecha_app_cuadrillas (id_campo, cuadrilla);

CREATE UNIQUE INDEX cosecha_app_usuarios_campo_usuario_uq
  ON cosecha_app_usuarios (id_campo, lower(usuario));

CREATE UNIQUE INDEX cosecha_app_usuarios_login_uq
  ON cosecha_app_usuarios (lower(login));

CREATE UNIQUE INDEX cosecha_app_contratistas_campo_nombre_uq
  ON cosecha_app_contratistas (id_campo, lower(btrim(contratistas, ' .'::text)));

CREATE INDEX cosecha_app_cuarteles_campo_idx ON cosecha_app_cuarteles (id_campo);
CREATE INDEX cosecha_app_escaneo_campo_idx ON cosecha_app_escaneo (id_campo);
CREATE INDEX cosecha_app_registro_campo_idx ON cosecha_app_registro (id_campo);
CREATE INDEX cosecha_app_qr_campo_idx ON cosecha_app_qr (id_campo);

COMMENT ON COLUMN cosecha_app_cuadrillas.cuadrilla IS
  'Número de cuadrilla, único dentro del campo. Otro campo puede repetir el 1.';

COMMENT ON COLUMN cosecha_app_usuarios.login IS
  'Login de AppSheet. codigo del campo, guion, usuario: isla-1, isla-admin.';

COMMENT ON COLUMN cosecha_app_usuarios.usuario IS
  'Número de la cuadrilla, o admin. Se repite en otro campo. El login no.';

-- La vista gana id_campo al final. El cálculo del pago no cambia.
CREATE OR REPLACE VIEW cosecha_app_resumen_bin_trabajador AS
 WITH base AS (
         SELECT e.id_registro,
            e.id_qr,
            e.id_bins,
            e.id_campo,
            COALESCE(e.fecha, (e.fecha_y_hora)::date) AS fecha,
            e.fecha_y_hora,
            COALESCE((e.precio_trato_aplicado)::numeric, (t.precio_capacho)::numeric) AS precio,
            COALESCE((e.piso_aplicado)::numeric, (t.piso_garantizado_diario)::numeric) AS piso_escaneo
           FROM (cosecha_app_escaneo e
             LEFT JOIN cosecha_app_tratos t ON ((t.id_trato = e.id_trato)))
          WHERE ((e.id_registro IS NOT NULL) AND (e.id_qr IS NOT NULL))
        ), agg AS (
         SELECT base.id_registro,
            base.id_qr,
            max(base.id_bins) AS id_bins,
            max(base.id_campo) AS id_campo,
            count(*) AS capachos,
            max(base.precio) AS valor_trato,
            max(base.piso_escaneo) AS piso_escaneo,
            max(base.fecha_y_hora) AS ultimo,
            (array_agg(base.fecha ORDER BY base.fecha_y_hora DESC NULLS LAST))[1] AS fecha
           FROM base
          GROUP BY base.id_registro, base.id_qr
        ), marcado AS (
         SELECT a.id_registro,
            a.id_qr,
            a.id_bins,
            a.id_campo,
            a.capachos,
            a.valor_trato,
            a.piso_escaneo,
            a.ultimo,
            a.fecha,
            s.accion_piso,
            s.comentario,
            row_number() OVER (PARTITION BY a.fecha, a.id_qr, a.id_campo ORDER BY a.ultimo DESC NULLS LAST, a.id_registro DESC) AS n
           FROM (agg a
             LEFT JOIN cosecha_app_salidas_trabajador s
               ON s.fecha = a.fecha AND s.id_qr = a.id_qr AND s.id_campo = a.id_campo)
        )
 SELECT ((id_registro || '-'::text) || id_qr) AS id_resumen,
    id_registro,
    id_qr,
    capachos,
    valor_trato,
    COALESCE(accion_piso, piso_escaneo) AS piso,
    ((capachos)::numeric * valor_trato) AS total_capachos,
    (((capachos)::numeric * valor_trato) +
        CASE
            WHEN (accion_piso IS NULL) THEN COALESCE(piso_escaneo, (0)::numeric)
            WHEN (n = 1) THEN accion_piso
            ELSE (0)::numeric
        END) AS total_a_recibir,
        CASE
            WHEN (accion_piso IS NULL) THEN NULL::text
            ELSE comentario
        END AS comentario,
    id_campo
   FROM marcado;

CREATE OR REPLACE VIEW cosecha_app_trabajadores_dia AS
 SELECT ((((to_char((fecha)::timestamp with time zone, 'YYYY-MM-DD'::text) || '|'::text) || id_cuadrilla) || '|'::text) || id_qr) AS id_trabajador_dia,
    fecha,
    id_cuadrilla,
    id_qr,
    trabajador,
    rut,
    (trabajador || COALESCE((' · '::text || rut), ''::text)) AS nombre_lista,
    capachos,
    ultimo_capacho,
    id_campo
   FROM ( SELECT COALESCE(e.fecha, (e.fecha_y_hora)::date) AS fecha,
            e.id_cuadrilla,
            e.id_qr,
            e.id_campo,
            max(e.trabajador) AS trabajador,
            max(e.rut_trabajador) AS rut,
            count(*) AS capachos,
            max(e.fecha_y_hora) AS ultimo_capacho
           FROM cosecha_app_escaneo e
          WHERE ((COALESCE(e.fecha, (e.fecha_y_hora)::date) >= (((CURRENT_TIMESTAMP AT TIME ZONE 'America/Santiago'::text))::date - 7)) AND (e.id_qr IS NOT NULL) AND (e.id_cuadrilla IS NOT NULL))
          GROUP BY COALESCE(e.fecha, (e.fecha_y_hora)::date), e.id_cuadrilla, e.id_qr, e.id_campo) dia;

COMMIT;
