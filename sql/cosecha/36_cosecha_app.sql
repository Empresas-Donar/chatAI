-- =============================================================================
-- Cosecha app: copia operativa del esquema de Zúñiga
--
-- Tablas appsheet.cosecha_app_*. No toca cosecha_zuniga_*.
-- Las funciones que nombran tablas son propias (cosecha_app_*).
-- Se reutilizan, sin modificarlas:
--   cosecha_clave_4d, cosecha_normaliza_lista_cuadrillas, set_recibido_en
--
-- Datos de arranque: configuración, los 13 cuarteles de Zúñiga y el admin.
-- La clave del admin es un placeholder. Cambiarla antes de usar la app.
-- Sin trato vigente, el registro de un bin se rechaza.
-- cultivo solo admite cereza o ciruela.
-- =============================================================================

BEGIN;

SET search_path TO appsheet, pg_catalog;
SET check_function_bodies = false;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_max_cuadrillas()
 RETURNS integer
 LANGUAGE sql
 STABLE
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
  SELECT COALESCE(
    (SELECT "value"::integer
     FROM cosecha_app_configuracion
     WHERE "key" = 'max_cuadrillas'),
    16
  )
$function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_valida_max_cuadrillas()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
DECLARE
  v_max int;
  v_bad bigint;
BEGIN
  v_max := cosecha_app_max_cuadrillas();

  SELECT MAX(x::bigint) INTO v_bad
  FROM regexp_split_to_table(COALESCE(NEW.cuadrillas, ''), '\s*,\s*') AS x
  WHERE x ~ '^\d+$'
    AND (x::bigint < 1 OR x::bigint > v_max);

  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'La cuadrilla % supera el máximo permitido (%)', v_bad, v_max;
  END IF;

  RETURN NEW;
END $function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_valida_numero_cuadrilla()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
DECLARE
  v_otra record;
  v_max int;
BEGIN
  IF current_setting('cosecha_app.syncing', true) = '1' THEN
    RETURN NEW;
  END IF;

  v_max := cosecha_app_max_cuadrillas();

  IF NEW.cuadrilla < 1 OR NEW.cuadrilla > v_max THEN
    RAISE EXCEPTION 'La cuadrilla % supera el máximo permitido (%)', NEW.cuadrilla, v_max;
  END IF;

  SELECT id_contratista
  INTO v_otra
  FROM cosecha_app_cuadrillas
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
END $function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_refresca_lista_contratista(p_id text)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
DECLARE
  v_lista text;
BEGIN
  IF p_id IS NULL THEN
    RETURN;
  END IF;

  SELECT string_agg(cuadrilla::text, ' , ' ORDER BY cuadrilla)
  INTO v_lista
  FROM cosecha_app_cuadrillas
  WHERE id_contratista = p_id;

  PERFORM set_config('cosecha_app.syncing', '1', true);
  UPDATE cosecha_app_contratistas
  SET cuadrillas = v_lista
  WHERE id_contratista = p_id
    AND cuadrillas IS DISTINCT FROM v_lista;
  PERFORM set_config('cosecha_app.syncing', '0', true);
END $function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_sync_cuadrillas_contratista()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
DECLARE
  v_num      bigint;
  v_cuad     record;
  v_nums     bigint[];
  v_id_cuad  text;
BEGIN
  -- La cuadrilla hija refresca esta lista. No volver a sincronizar.
  IF current_setting('cosecha_app.syncing', true) = '1' THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
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
    WHERE cuadrilla::numeric = v_num;

    IF FOUND THEN
      IF v_cuad.id_contratista IS NOT NULL
         AND v_cuad.id_contratista <> NEW.id_contratista THEN
        RAISE EXCEPTION 'La cuadrilla % ya pertenece a otro contratista', v_num;
      END IF;

      UPDATE cosecha_app_cuadrillas
      SET id_contratista = NEW.id_contratista
      WHERE id_cuadrilla = v_cuad.id_cuadrilla;

      v_id_cuad := v_cuad.id_cuadrilla;
    ELSE
      v_id_cuad := substr(md5(random()::text || clock_timestamp()::text), 1, 8);
      INSERT INTO cosecha_app_cuadrillas
        (id_cuadrilla, id_contratista, cuadrilla, fecha_y_hora)
      VALUES (v_id_cuad, NEW.id_contratista, v_num, now());
    END IF;

    IF EXISTS (
      SELECT 1 FROM cosecha_app_usuarios WHERE id_cuadrilla = v_id_cuad
    ) THEN
      UPDATE cosecha_app_usuarios
      SET activo = true, usuario = v_num::text, rol = 'cuadrilla'
      WHERE id_cuadrilla = v_id_cuad;
    ELSE
      INSERT INTO cosecha_app_usuarios
        (usuarioid, usuario, "contraseña", rol, id_cuadrilla, activo, creado_en)
      VALUES
        (substr(md5(random()::text || clock_timestamp()::text), 1, 8),
         v_num::text, cosecha_clave_4d(), 'cuadrilla', v_id_cuad, true, now());
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
END $function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_sync_desde_cuadrilla()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
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
    AND id_cuadrilla <> NEW.id_cuadrilla;

  IF FOUND THEN
    IF v_otra.id_contratista IS NULL THEN
      RAISE EXCEPTION
        'La cuadrilla % está libre. Reasígnela en vez de crear otra', NEW.cuadrilla;
    END IF;
    RAISE EXCEPTION 'La cuadrilla % ya pertenece a otro contratista', NEW.cuadrilla;
  END IF;

  IF EXISTS (
    SELECT 1 FROM cosecha_app_usuarios WHERE id_cuadrilla = NEW.id_cuadrilla
  ) THEN
    UPDATE cosecha_app_usuarios
    SET activo = (NEW.id_contratista IS NOT NULL),
        usuario = NEW.cuadrilla::text,
        rol = 'cuadrilla'
    WHERE id_cuadrilla = NEW.id_cuadrilla;
  ELSE
    INSERT INTO cosecha_app_usuarios
      (usuarioid, usuario, "contraseña", rol, id_cuadrilla, activo, creado_en)
    VALUES
      (substr(md5(random()::text || clock_timestamp()::text), 1, 8),
       NEW.cuadrilla::text, cosecha_clave_4d(), 'cuadrilla', NEW.id_cuadrilla,
       (NEW.id_contratista IS NOT NULL), now());
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.id_contratista IS DISTINCT FROM NEW.id_contratista THEN
    PERFORM cosecha_app_refresca_lista_contratista(OLD.id_contratista);
  END IF;
  PERFORM cosecha_app_refresca_lista_contratista(NEW.id_contratista);

  RETURN NEW;
END $function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_trato_para(p_cuartel text, p_fecha date)
 RETURNS text
 LANGUAGE sql
 STABLE
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
  SELECT t.id_trato
  FROM cosecha_app_tratos t
  JOIN cosecha_app_tratos_cuarteles tc ON tc.id_trato = t.id_trato
  WHERE tc.id_cuartel = p_cuartel
    AND t.fecha_inicio_vigencia <= p_fecha
  ORDER BY t.fecha_inicio_vigencia DESC
  LIMIT 1
$function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_registro_bin()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
DECLARE
  v_trato text;
BEGIN
  IF NEW.id_bins IS NULL OR NEW.id_bins = '' THEN
    RAISE EXCEPTION 'El registro no trae id_bins';
  END IF;
  IF NEW.bins IS NULL THEN
    RAISE EXCEPTION 'Falta el código del bin';
  END IF;

  v_trato := cosecha_app_trato_para(NEW.id_cuartel, NEW.fecha_y_hora::date);
  IF v_trato IS NULL THEN
    RAISE EXCEPTION
      'No hay trato vigente para el cuartel % al %',
      NEW.id_cuartel, NEW.fecha_y_hora::date;
  END IF;

  INSERT INTO cosecha_app_bins (id_bins, bins, id_trato)
  VALUES (NEW.id_bins, NEW.bins, v_trato)
  ON CONFLICT (id_bins) DO UPDATE
    SET bins = EXCLUDED.bins,
        id_trato = EXCLUDED.id_trato;

  IF TG_OP = 'UPDATE' THEN
    UPDATE cosecha_app_escaneo e
    SET id_trato = v_trato,
        bins = NEW.bins::text,
        precio_trato_aplicado = t.precio_capacho,
        piso_aplicado = t.piso_garantizado_diario
    FROM cosecha_app_tratos t
    WHERE e.id_bins = NEW.id_bins
      AND t.id_trato = v_trato
      AND (
        e.id_trato IS DISTINCT FROM v_trato
        OR e.bins IS DISTINCT FROM NEW.bins::text
        OR e.precio_trato_aplicado IS DISTINCT FROM t.precio_capacho
        OR e.piso_aplicado IS DISTINCT FROM t.piso_garantizado_diario
      );
  END IF;

  RETURN NEW;
END $function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_escaneo_trato()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
BEGIN
  SELECT b.id_trato, b.bins::text, t.precio_capacho, t.piso_garantizado_diario
    INTO NEW.id_trato, NEW.bins, NEW.precio_trato_aplicado, NEW.piso_aplicado
  FROM cosecha_app_bins b
  LEFT JOIN cosecha_app_tratos t ON t.id_trato = b.id_trato
  WHERE b.id_bins = NEW.id_bins;
  RETURN NEW;
END $function$;

CREATE OR REPLACE FUNCTION appsheet.cosecha_app_salidas_lote_expandir()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'appsheet', 'pg_catalog'
AS $function$
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
   WHERE r.id_registro = NEW.id_registro;

  IF v_bins IS NULL THEN
    RAISE EXCEPTION 'El registro % no tiene bin', NEW.id_registro;
  END IF;

  SELECT c.cuadrilla::text
    INTO v_cuadrilla
    FROM cosecha_app_cuadrillas c
   WHERE c.id_cuadrilla = NEW.id_cuadrilla;

  FOREACH k IN ARRAY regexp_split_to_array(trim(NEW.trabajadores), '\s*,\s*')
  LOOP
    CONTINUE WHEN k IS NULL OR btrim(k) = '';
    k := btrim(k);

    -- Formato nuevo: id_registro-id_qr. Formato viejo: fecha|cuadrilla|id_qr.
    IF position('|' IN k) > 0 THEN
      v_id_qr := split_part(k, '|', 3);
    ELSE
      v_id_qr := substring(k FROM position('-' IN k) + 1);
    END IF;

    IF v_id_qr IS NULL OR btrim(v_id_qr) = '' THEN
      RAISE EXCEPTION 'Clave de trabajador inválida: %', k;
    END IF;

    -- Nombre, hora y trato salen del bin que se marcó. La fecha cubre
    -- los demás bins del día.
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
     ORDER BY es.fecha_y_hora DESC
     LIMIT 1;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'No hay escaneos de % en el registro %', v_id_qr, NEW.id_registro;
    END IF;

    v_fecha := e.fecha;

    DELETE FROM cosecha_app_salidas_trabajador
     WHERE id_qr = v_id_qr
       AND fecha = v_fecha;

    INSERT INTO cosecha_app_salidas_trabajador (
      id_salida, fecha, id_qr, trabajador, rut, codigo_qr, accion_piso,
      comentario, hora_salida, registrado_por, id_bins, id_trato, created_at
    ) VALUES (
      'salida-' || to_char(v_fecha, 'YYYYMMDD') || '-' || v_id_qr,
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
      now()
    );
  END LOOP;

  RETURN NEW;
END $function$;

CREATE TABLE appsheet.cosecha_app_bins (
    id_bins text NOT NULL,
    bins integer,
    id_trato text
);

--
-- Name: COLUMN cosecha_app_bins.id_bins; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_bins.id_bins IS 'Id de sistema. El código en bins puede repetirse.';

--
-- Name: COLUMN cosecha_app_bins.bins; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_bins.bins IS 'Código del bin, por ejemplo 1212. No es único.';

--
-- Name: COLUMN cosecha_app_bins.id_trato; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_bins.id_trato IS 'Ref a cosecha_app_tratos. El precio de esta apertura.';

--
-- Name: cosecha_app_configuracion; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_configuracion (
    key text NOT NULL,
    value text NOT NULL,
    CONSTRAINT cosecha_app_configuracion_valor_chk CHECK ((((key = 'espera_activa'::text) AND (value = ANY (ARRAY['true'::text, 'false'::text]))) OR ((key = 'espera_segundos'::text) AND (value ~ '^\d+$'::text)) OR ((key = 'max_cuadrillas'::text) AND (value ~ '^[1-9][0-9]*$'::text)) OR (key <> ALL (ARRAY['espera_activa'::text, 'espera_segundos'::text, 'max_cuadrillas'::text]))))
);

--
-- Name: TABLE cosecha_app_configuracion; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON TABLE appsheet.cosecha_app_configuracion IS 'Ajustes de la app. Una fila por key.';

--
-- Name: COLUMN cosecha_app_configuracion.key; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_configuracion.key IS 'Nombre del ajuste: espera_activa, espera_segundos, max_cuadrillas.';

--
-- Name: COLUMN cosecha_app_configuracion.value; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_configuracion.value IS 'Valor en texto. max_cuadrillas y espera_segundos son enteros.';

--
-- Name: cosecha_app_contratistas; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_contratistas (
    id_contratista text NOT NULL,
    fecha_y_hora timestamp without time zone DEFAULT now() NOT NULL,
    contratistas text NOT NULL,
    cuadrillas text,
    id_ultfecha text,
    comentario text,
    id_intranet_contratistas text,
    CONSTRAINT cosecha_app_contratistas_nombre_chk CHECK ((btrim(contratistas) <> ''::text))
);

--
-- Name: TABLE cosecha_app_contratistas; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON TABLE appsheet.cosecha_app_contratistas IS 'Un contratista por nombre. Las cuadrillas están en cosecha_app_cuadrillas.';

--
-- Name: COLUMN cosecha_app_contratistas.cuadrillas; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_contratistas.cuadrillas IS 'EnumList AppSheet ("1 , 2 , 3"). El trigger sincroniza cuadrillas y el acceso de cada número.';

--
-- Name: COLUMN cosecha_app_contratistas.comentario; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_contratistas.comentario IS 'Nota del contratista, no de una cuadrilla.';

--
-- Name: COLUMN cosecha_app_contratistas.id_intranet_contratistas; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_contratistas.id_intranet_contratistas IS 'Texto nullable hacia intranet.contratistas.id_intranet. Sin FK. NULL si no hay enlace.';

--
-- Name: cosecha_app_cuadrillas; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_cuadrillas (
    id_cuadrilla text NOT NULL,
    id_contratista text,
    cuadrilla integer NOT NULL,
    fecha_y_hora timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT cosecha_app_cuadrillas_numero_chk CHECK ((cuadrilla > 0))
);

--
-- Name: TABLE cosecha_app_cuadrillas; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON TABLE appsheet.cosecha_app_cuadrillas IS 'Cuadrillas de un contratista. id_cuadrilla reutiliza el id original de contratistas.';

--
-- Name: COLUMN cosecha_app_cuadrillas.id_contratista; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_cuadrillas.id_contratista IS 'NULL si la cuadrilla no está asignada. El trigger la libera al quitarla de la lista.';

--
-- Name: COLUMN cosecha_app_cuadrillas.cuadrilla; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_cuadrillas.cuadrilla IS 'Número de cuadrilla, único en toda la empresa.';

--
-- Name: cosecha_app_cuarteles; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_cuarteles (
    id_cuartel text NOT NULL,
    nombre_cuartel text,
    variedad text,
    cultivo text NOT NULL,
    CONSTRAINT cosecha_app_cuarteles_cultivo_chk CHECK ((cultivo = ANY (ARRAY['cereza'::text, 'ciruela'::text])))
);

--
-- Name: COLUMN cosecha_app_cuarteles.cultivo; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_cuarteles.cultivo IS 'cereza o ciruela. Ciruela solo en CC-860 CIRUELOS ADULTOS.';

--
-- Name: cosecha_app_escaneo; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_escaneo (
    id_escaneo text,
    codigo_qr text,
    fecha date,
    fecha_y_hora timestamp without time zone,
    cuartel text,
    variedad text,
    bins text,
    contratista text,
    cuadrilla numeric(12,2),
    trabajador text,
    rut_trabajador text,
    id_fecha text,
    precio_trato_aplicado numeric(12,2),
    piso_aplicado numeric(12,2),
    fecha_solo_dia date,
    id_registro text,
    id_qr text,
    id_cuadrilla text NOT NULL,
    id_contratista text NOT NULL,
    id_bins text,
    id_trato text,
    recibido_en timestamp with time zone
);

--
-- Name: COLUMN cosecha_app_escaneo.precio_trato_aplicado; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_escaneo.precio_trato_aplicado IS 'Precio del capacho copiado del trato al escanear.';

--
-- Name: COLUMN cosecha_app_escaneo.piso_aplicado; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_escaneo.piso_aplicado IS 'Piso diario copiado del trato al escanear.';

--
-- Name: COLUMN cosecha_app_escaneo.id_trato; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_escaneo.id_trato IS 'Lo llena el trigger desde el bin.';

--
-- Name: COLUMN cosecha_app_escaneo.recibido_en; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_escaneo.recibido_en IS 'Hora en que la base recibió el escaneo. La llena el trigger al insertar.';

--
-- Name: cosecha_app_filtros; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_filtros (
    usuario character varying(255) NOT NULL,
    desde date,
    hasta date
);

--
-- Name: cosecha_app_qr; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_qr (
    id_qr text,
    qr_trabajador text,
    cuadrilla text,
    trabajador text,
    rut text,
    id_fecha text,
    id_cuadrilla text NOT NULL,
    id_contratista text NOT NULL
);

--
-- Name: cosecha_app_registro; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_registro (
    id_registro text,
    fecha_y_hora timestamp without time zone,
    cuadrilla integer,
    id_contratista text NOT NULL,
    id_cuartel text,
    variedad text,
    bins integer,
    id_fecha text,
    unnamed text,
    nombre_cuartel_texto text,
    id_cuadrilla text NOT NULL,
    id_bins text,
    cultivo text
);

--
-- Name: COLUMN cosecha_app_registro.id_contratista; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_registro.id_contratista IS 'Ref a cosecha_app_contratistas.';

--
-- Name: COLUMN cosecha_app_registro.id_cuartel; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_registro.id_cuartel IS 'Ref a cosecha_app_cuarteles. El nombre sigue en nombre_cuartel_texto.';

--
-- Name: COLUMN cosecha_app_registro.id_bins; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_registro.id_bins IS 'Id de sistema del bin. Sin FK: AppSheet crea bin y registro juntos.';

--
-- Name: COLUMN cosecha_app_registro.cultivo; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_registro.cultivo IS 'cereza o ciruela, copiado del cuartel.';

--
-- Name: cosecha_app_salidas_trabajador; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_salidas_trabajador (
    id_salida text NOT NULL,
    fecha date NOT NULL,
    id_qr text NOT NULL,
    accion_piso numeric NOT NULL,
    comentario text,
    hora_salida timestamp without time zone NOT NULL,
    registrado_por text,
    id_bins text,
    id_trato text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    trabajador text,
    rut text,
    codigo_qr text,
    CONSTRAINT cosecha_app_salidas_trabajador_accion_piso_check CHECK ((accion_piso >= (0)::numeric))
);

--
-- Name: TABLE cosecha_app_salidas_trabajador; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON TABLE appsheet.cosecha_app_salidas_trabajador IS 'Reemplazo del piso de un trabajador en una fecha. Vale para todos los bins de ese día. Sin fila, cada bin paga el piso del escaneo.';

--
-- Name: COLUMN cosecha_app_salidas_trabajador.accion_piso; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_salidas_trabajador.accion_piso IS 'Piso que reemplaza al del trato, en CLP. 0 no paga piso.';

--
-- Name: COLUMN cosecha_app_salidas_trabajador.hora_salida; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_salidas_trabajador.hora_salida IS 'Hora del hecho. created_at es cuándo se registró.';

--
-- Name: COLUMN cosecha_app_salidas_trabajador.trabajador; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_salidas_trabajador.trabajador IS 'Nombre con el que escaneó ese día.';

--
-- Name: COLUMN cosecha_app_salidas_trabajador.rut; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_salidas_trabajador.rut IS 'RUT con el que escaneó ese día.';

--
-- Name: COLUMN cosecha_app_salidas_trabajador.codigo_qr; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_salidas_trabajador.codigo_qr IS 'Código QR que usó ese día, el de escaneo.codigo_qr.';

--
-- Name: cosecha_app_tratos; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_tratos (
    id_trato text NOT NULL,
    fecha_inicio_vigencia date,
    cuartel_id text,
    nombre_cuartel text,
    precio_capacho integer,
    piso_garantizado_diario numeric(12,0)
);

--
-- Name: COLUMN cosecha_app_tratos.piso_garantizado_diario; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_tratos.piso_garantizado_diario IS 'Valor mínimo diario garantizado por trabajador (CLP)';

--
-- Name: cosecha_app_resumen_bin_trabajador; Type: VIEW; Schema: appsheet; Owner: -
--

CREATE VIEW appsheet.cosecha_app_resumen_bin_trabajador AS
 WITH base AS (
         SELECT e.id_registro,
            e.id_qr,
            e.id_bins,
            COALESCE(e.fecha, (e.fecha_y_hora)::date) AS fecha,
            e.fecha_y_hora,
            COALESCE((e.precio_trato_aplicado)::numeric, (t.precio_capacho)::numeric) AS precio,
            COALESCE((e.piso_aplicado)::numeric, (t.piso_garantizado_diario)::numeric) AS piso_escaneo
           FROM (appsheet.cosecha_app_escaneo e
             LEFT JOIN appsheet.cosecha_app_tratos t ON ((t.id_trato = e.id_trato)))
          WHERE ((e.id_registro IS NOT NULL) AND (e.id_qr IS NOT NULL))
        ), agg AS (
         SELECT base.id_registro,
            base.id_qr,
            max(base.id_bins) AS id_bins,
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
            a.capachos,
            a.valor_trato,
            a.piso_escaneo,
            a.ultimo,
            a.fecha,
            s.accion_piso,
            s.comentario,
            row_number() OVER (PARTITION BY a.fecha, a.id_qr ORDER BY a.ultimo DESC NULLS LAST, a.id_registro DESC) AS n
           FROM (agg a
             LEFT JOIN appsheet.cosecha_app_salidas_trabajador s ON (((s.fecha = a.fecha) AND (s.id_qr = a.id_qr))))
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
        END AS comentario
   FROM marcado;

--
-- Name: VIEW cosecha_app_resumen_bin_trabajador; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON VIEW appsheet.cosecha_app_resumen_bin_trabajador IS 'Capachos, trato y piso por bin. Si hay salida ese día, el piso de todos los bins es accion_piso y el monto entra una vez, en el bin del último capacho.';

--
-- Name: COLUMN cosecha_app_resumen_bin_trabajador.comentario; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_resumen_bin_trabajador.comentario IS 'Motivo guardado al modificar el piso de ese bin. Vacío si el piso es el del escaneo.';

--
-- Name: cosecha_app_salidas_lote; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_salidas_lote (
    id_lote text NOT NULL,
    fecha date NOT NULL,
    id_cuadrilla text NOT NULL,
    id_registro text,
    trabajadores text NOT NULL,
    accion_piso numeric NOT NULL,
    observacion text,
    registrado_por text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT cosecha_app_salidas_lote_accion_piso_check CHECK ((accion_piso >= (0)::numeric))
);

--
-- Name: TABLE cosecha_app_salidas_lote; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON TABLE appsheet.cosecha_app_salidas_lote IS 'Formulario de abandono. Una fila es un lote: varios trabajadores, un piso, una observación.';

--
-- Name: COLUMN cosecha_app_salidas_lote.trabajadores; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_salidas_lote.trabajadores IS 'EnumList. Cada valor es el id de Resumen Bin (id_registro-id_qr) o la clave vieja fecha|id_cuadrilla|id_qr.';

--
-- Name: COLUMN cosecha_app_salidas_lote.accion_piso; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_salidas_lote.accion_piso IS 'Piso en CLP que escribe el supervisor. Reemplaza al piso del escaneo. 0 no paga piso.';

--
-- Name: cosecha_app_trabajadores_dia; Type: VIEW; Schema: appsheet; Owner: -
--

CREATE VIEW appsheet.cosecha_app_trabajadores_dia AS
 SELECT ((((to_char((fecha)::timestamp with time zone, 'YYYY-MM-DD'::text) || '|'::text) || id_cuadrilla) || '|'::text) || id_qr) AS id_trabajador_dia,
    fecha,
    id_cuadrilla,
    id_qr,
    trabajador,
    rut,
    (trabajador || COALESCE((' · '::text || rut), ''::text)) AS nombre_lista,
    capachos,
    ultimo_capacho
   FROM ( SELECT COALESCE(e.fecha, (e.fecha_y_hora)::date) AS fecha,
            e.id_cuadrilla,
            e.id_qr,
            max(e.trabajador) AS trabajador,
            max(e.rut_trabajador) AS rut,
            count(*) AS capachos,
            max(e.fecha_y_hora) AS ultimo_capacho
           FROM appsheet.cosecha_app_escaneo e
          WHERE ((COALESCE(e.fecha, (e.fecha_y_hora)::date) >= (((CURRENT_TIMESTAMP AT TIME ZONE 'America/Santiago'::text))::date - 7)) AND (e.id_qr IS NOT NULL) AND (e.id_cuadrilla IS NOT NULL))
          GROUP BY COALESCE(e.fecha, (e.fecha_y_hora)::date), e.id_cuadrilla, e.id_qr) dia;

--
-- Name: VIEW cosecha_app_trabajadores_dia; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON VIEW appsheet.cosecha_app_trabajadores_dia IS 'Personas que escanearon en cada cuadrilla, últimos 7 días. La clave del EnumList es id_trabajador_dia.';

--
-- Name: cosecha_app_tratos_cuarteles; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_tratos_cuarteles (
    id_trato_cuartel text NOT NULL,
    id_trato text NOT NULL,
    id_cuartel text NOT NULL
);

--
-- Name: cosecha_app_usuarios; Type: TABLE; Schema: appsheet; Owner: -
--

CREATE TABLE appsheet.cosecha_app_usuarios (
    usuarioid text DEFAULT (gen_random_uuid())::text NOT NULL,
    usuario text NOT NULL,
    "contraseña" text DEFAULT '1234'::text NOT NULL,
    rol text DEFAULT 'cuadrilla'::text NOT NULL,
    id_cuadrilla text,
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cosecha_app_usuarios_cuadrilla_chk CHECK (((rol <> 'cuadrilla'::text) OR (id_cuadrilla IS NOT NULL))),
    CONSTRAINT cosecha_app_usuarios_rol_chk CHECK ((rol = ANY (ARRAY['admin'::text, 'cuadrilla'::text])))
);

--
-- Name: TABLE cosecha_app_usuarios; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON TABLE appsheet.cosecha_app_usuarios IS 'Login de la app. admin no tiene cuadrilla; cuadrilla exige id_cuadrilla.';

--
-- Name: COLUMN cosecha_app_usuarios."contraseña"; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_usuarios."contraseña" IS 'Secreto en texto plano. No seleccionarla, no loguearla, no exportarla.';

--
-- Name: COLUMN cosecha_app_usuarios.id_cuadrilla; Type: COMMENT; Schema: appsheet; Owner: -
--

COMMENT ON COLUMN appsheet.cosecha_app_usuarios.id_cuadrilla IS 'Ref a cosecha_app_cuadrillas. NULL solo si rol = admin.';

--
-- Name: cosecha_app_bins cosecha_app_bins_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_bins
    ADD CONSTRAINT cosecha_app_bins_pkey PRIMARY KEY (id_bins);

--
-- Name: cosecha_app_configuracion cosecha_app_configuracion_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_configuracion
    ADD CONSTRAINT cosecha_app_configuracion_pkey PRIMARY KEY (key);

--
-- Name: cosecha_app_contratistas cosecha_app_contratistas_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_contratistas
    ADD CONSTRAINT cosecha_app_contratistas_pkey PRIMARY KEY (id_contratista);

--
-- Name: cosecha_app_cuadrillas cosecha_app_cuadrillas_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_cuadrillas
    ADD CONSTRAINT cosecha_app_cuadrillas_pkey PRIMARY KEY (id_cuadrilla);

--
-- Name: cosecha_app_cuarteles cosecha_app_cuarteles_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_cuarteles
    ADD CONSTRAINT cosecha_app_cuarteles_pkey PRIMARY KEY (id_cuartel);

--
-- Name: cosecha_app_filtros cosecha_app_filtros_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_filtros
    ADD CONSTRAINT cosecha_app_filtros_pkey PRIMARY KEY (usuario);

--
-- Name: cosecha_app_salidas_trabajador cosecha_app_salidas_fecha_qr; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_salidas_trabajador
    ADD CONSTRAINT cosecha_app_salidas_fecha_qr UNIQUE (fecha, id_qr);

--
-- Name: cosecha_app_salidas_lote cosecha_app_salidas_lote_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_salidas_lote
    ADD CONSTRAINT cosecha_app_salidas_lote_pkey PRIMARY KEY (id_lote);

--
-- Name: cosecha_app_salidas_trabajador cosecha_app_salidas_trabajador_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_salidas_trabajador
    ADD CONSTRAINT cosecha_app_salidas_trabajador_pkey PRIMARY KEY (id_salida);

--
-- Name: cosecha_app_tratos_cuarteles cosecha_app_tratos_cuarteles_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_tratos_cuarteles
    ADD CONSTRAINT cosecha_app_tratos_cuarteles_pkey PRIMARY KEY (id_trato_cuartel);

--
-- Name: cosecha_app_tratos cosecha_app_tratos_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_tratos
    ADD CONSTRAINT cosecha_app_tratos_pkey PRIMARY KEY (id_trato);

--
-- Name: cosecha_app_usuarios cosecha_app_usuarios_pkey; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_usuarios
    ADD CONSTRAINT cosecha_app_usuarios_pkey PRIMARY KEY (usuarioid);

--
-- Name: cosecha_app_tratos_cuarteles cosecha_app_trato_cuartel_uq; Type: CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_tratos_cuarteles
    ADD CONSTRAINT cosecha_app_trato_cuartel_uq UNIQUE (id_trato, id_cuartel);

--
-- Name: cosecha_app_contratistas_nombre_norm_uq; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE UNIQUE INDEX cosecha_app_contratistas_nombre_norm_uq ON appsheet.cosecha_app_contratistas USING btree (lower(btrim(contratistas, ' .'::text)));

--
-- Name: cosecha_app_cuadrillas_contratista_numero_uq; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE UNIQUE INDEX cosecha_app_cuadrillas_contratista_numero_uq ON appsheet.cosecha_app_cuadrillas USING btree (id_contratista, cuadrilla);

--
-- Name: cosecha_app_cuadrillas_numero_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_cuadrillas_numero_idx ON appsheet.cosecha_app_cuadrillas USING btree (cuadrilla);

--
-- Name: cosecha_app_usuarios_id_cuadrilla_uq; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE UNIQUE INDEX cosecha_app_usuarios_id_cuadrilla_uq ON appsheet.cosecha_app_usuarios USING btree (id_cuadrilla) WHERE (id_cuadrilla IS NOT NULL);

--
-- Name: cosecha_app_usuarios_usuario_uq; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE UNIQUE INDEX cosecha_app_usuarios_usuario_uq ON appsheet.cosecha_app_usuarios USING btree (lower(usuario));

--
-- Name: cosecha_app_salidas_bins_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_salidas_bins_idx ON appsheet.cosecha_app_salidas_trabajador USING btree (id_bins);

--
-- Name: cosecha_app_bins_id_trato_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_bins_id_trato_idx ON appsheet.cosecha_app_bins USING btree (id_trato);

--
-- Name: cosecha_app_escaneo_id_bins_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_escaneo_id_bins_idx ON appsheet.cosecha_app_escaneo USING btree (id_bins);

--
-- Name: cosecha_app_qr_id_cuadrilla_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_qr_id_cuadrilla_idx ON appsheet.cosecha_app_qr USING btree (id_cuadrilla);

--
-- Name: cosecha_app_registro_id_bins_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_registro_id_bins_idx ON appsheet.cosecha_app_registro USING btree (id_bins);

--
-- Name: cosecha_app_registro_id_contratista_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_registro_id_contratista_idx ON appsheet.cosecha_app_registro USING btree (id_contratista);

--
-- Name: cosecha_app_registro_id_cuadrilla_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_registro_id_cuadrilla_idx ON appsheet.cosecha_app_registro USING btree (id_cuadrilla);

--
-- Name: cosecha_app_registro_id_cuartel_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_registro_id_cuartel_idx ON appsheet.cosecha_app_registro USING btree (id_cuartel);

--
-- Name: cosecha_app_tratos_cuarteles_cuartel_idx; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE INDEX cosecha_app_tratos_cuarteles_cuartel_idx ON appsheet.cosecha_app_tratos_cuarteles USING btree (id_cuartel);

--
-- Name: cosecha_app_cuadrillas_numero_uq; Type: INDEX; Schema: appsheet; Owner: -
--

CREATE UNIQUE INDEX cosecha_app_cuadrillas_numero_uq ON appsheet.cosecha_app_cuadrillas USING btree (((cuadrilla)::numeric));

--
-- Name: cosecha_app_contratistas trg_contratistas_libera_cuadrillas; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_contratistas_libera_cuadrillas BEFORE DELETE ON appsheet.cosecha_app_contratistas FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_app_sync_cuadrillas_contratista();

--
-- Name: cosecha_app_contratistas trg_contratistas_normaliza; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_contratistas_normaliza BEFORE INSERT OR UPDATE OF cuadrillas ON appsheet.cosecha_app_contratistas FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_normaliza_lista_cuadrillas();

--
-- Name: cosecha_app_contratistas trg_contratistas_sync_cuadrillas; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_contratistas_sync_cuadrillas AFTER INSERT OR UPDATE OF cuadrillas ON appsheet.cosecha_app_contratistas FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_app_sync_cuadrillas_contratista();

--
-- Name: cosecha_app_contratistas trg_contratistas_valida_max; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_contratistas_valida_max BEFORE INSERT OR UPDATE OF cuadrillas ON appsheet.cosecha_app_contratistas FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_app_valida_max_cuadrillas();

--
-- Name: cosecha_app_escaneo trg_cosecha_escaneo_trato; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_cosecha_escaneo_trato BEFORE INSERT OR UPDATE OF id_bins ON appsheet.cosecha_app_escaneo FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_app_escaneo_trato();

--
-- Name: cosecha_app_registro trg_cosecha_registro_bin; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_cosecha_registro_bin BEFORE INSERT OR UPDATE OF id_bins, bins, id_cuartel, fecha_y_hora ON appsheet.cosecha_app_registro FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_app_registro_bin();

--
-- Name: cosecha_app_cuadrillas trg_cuadrillas_sync_acceso; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_cuadrillas_sync_acceso AFTER INSERT OR DELETE OR UPDATE OF cuadrilla, id_contratista ON appsheet.cosecha_app_cuadrillas FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_app_sync_desde_cuadrilla();

--
-- Name: cosecha_app_cuadrillas trg_cuadrillas_valida_numero; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_cuadrillas_valida_numero BEFORE INSERT OR UPDATE OF cuadrilla, id_contratista ON appsheet.cosecha_app_cuadrillas FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_app_valida_numero_cuadrilla();

--
-- Name: cosecha_app_escaneo trg_escaneo_recibido; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_escaneo_recibido BEFORE INSERT ON appsheet.cosecha_app_escaneo FOR EACH ROW EXECUTE FUNCTION appsheet.set_recibido_en();

--
-- Name: cosecha_app_salidas_lote trg_salidas_lote_expandir; Type: TRIGGER; Schema: appsheet; Owner: -
--

CREATE TRIGGER trg_salidas_lote_expandir AFTER INSERT ON appsheet.cosecha_app_salidas_lote FOR EACH ROW EXECUTE FUNCTION appsheet.cosecha_app_salidas_lote_expandir();

--
-- Name: cosecha_app_bins cosecha_app_bins_trato_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_bins
    ADD CONSTRAINT cosecha_app_bins_trato_fk FOREIGN KEY (id_trato) REFERENCES appsheet.cosecha_app_tratos(id_trato);

--
-- Name: cosecha_app_cuadrillas cosecha_app_cuadrillas_contratista_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_cuadrillas
    ADD CONSTRAINT cosecha_app_cuadrillas_contratista_fk FOREIGN KEY (id_contratista) REFERENCES appsheet.cosecha_app_contratistas(id_contratista);

--
-- Name: cosecha_app_escaneo cosecha_app_escaneo_bins_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_escaneo
    ADD CONSTRAINT cosecha_app_escaneo_bins_fk FOREIGN KEY (id_bins) REFERENCES appsheet.cosecha_app_bins(id_bins);

--
-- Name: cosecha_app_escaneo cosecha_app_escaneo_trato_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_escaneo
    ADD CONSTRAINT cosecha_app_escaneo_trato_fk FOREIGN KEY (id_trato) REFERENCES appsheet.cosecha_app_tratos(id_trato);

--
-- Name: cosecha_app_registro cosecha_app_registro_bins_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_registro
    ADD CONSTRAINT cosecha_app_registro_bins_fk FOREIGN KEY (id_bins) REFERENCES appsheet.cosecha_app_bins(id_bins) NOT VALID;

--
-- Name: cosecha_app_registro cosecha_app_registro_contratista_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_registro
    ADD CONSTRAINT cosecha_app_registro_contratista_fk FOREIGN KEY (id_contratista) REFERENCES appsheet.cosecha_app_contratistas(id_contratista);

--
-- Name: cosecha_app_registro cosecha_app_registro_cuadrilla_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_registro
    ADD CONSTRAINT cosecha_app_registro_cuadrilla_fk FOREIGN KEY (id_cuadrilla) REFERENCES appsheet.cosecha_app_cuadrillas(id_cuadrilla);

--
-- Name: cosecha_app_registro cosecha_app_registro_cuartel_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_registro
    ADD CONSTRAINT cosecha_app_registro_cuartel_fk FOREIGN KEY (id_cuartel) REFERENCES appsheet.cosecha_app_cuarteles(id_cuartel);

--
-- Name: cosecha_app_salidas_trabajador cosecha_app_salidas_trabajador_id_bins_fkey; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_salidas_trabajador
    ADD CONSTRAINT cosecha_app_salidas_trabajador_id_bins_fkey FOREIGN KEY (id_bins) REFERENCES appsheet.cosecha_app_bins(id_bins);

--
-- Name: cosecha_app_salidas_trabajador cosecha_app_salidas_trabajador_id_trato_fkey; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_salidas_trabajador
    ADD CONSTRAINT cosecha_app_salidas_trabajador_id_trato_fkey FOREIGN KEY (id_trato) REFERENCES appsheet.cosecha_app_tratos(id_trato);

--
-- Name: cosecha_app_tratos_cuarteles cosecha_app_tratos_cuarteles_id_cuartel_fkey; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_tratos_cuarteles
    ADD CONSTRAINT cosecha_app_tratos_cuarteles_id_cuartel_fkey FOREIGN KEY (id_cuartel) REFERENCES appsheet.cosecha_app_cuarteles(id_cuartel);

--
-- Name: cosecha_app_tratos_cuarteles cosecha_app_tratos_cuarteles_id_trato_fkey; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_tratos_cuarteles
    ADD CONSTRAINT cosecha_app_tratos_cuarteles_id_trato_fkey FOREIGN KEY (id_trato) REFERENCES appsheet.cosecha_app_tratos(id_trato) ON DELETE CASCADE;

--
-- Name: cosecha_app_usuarios cosecha_app_usuarios_cuadrilla_fk; Type: FK CONSTRAINT; Schema: appsheet; Owner: -
--

ALTER TABLE ONLY appsheet.cosecha_app_usuarios
    ADD CONSTRAINT cosecha_app_usuarios_cuadrilla_fk FOREIGN KEY (id_cuadrilla) REFERENCES appsheet.cosecha_app_cuadrillas(id_cuadrilla) ON DELETE CASCADE;

--

-- -----------------------------------------------------------------------------
-- Datos de arranque
-- -----------------------------------------------------------------------------

INSERT INTO cosecha_app_configuracion ("key", "value") VALUES
  ('espera_activa', 'true'),
  ('espera_segundos', '240'),
  ('max_cuadrillas', '24');

INSERT INTO cosecha_app_cuarteles (id_cuartel, nombre_cuartel, variedad, cultivo) VALUES
  ('C01', '881 Lapins 2014', 'Lapins', 'cereza'),
  ('C02', '884 Lapins 2015', 'Lapins', 'cereza'),
  ('C03', '891 Lapins 2019', 'Lapins', 'cereza'),
  ('C04', '883 Santina 2014', 'Santina', 'cereza'),
  ('C05', '895 Santina 2018', 'Santina', 'cereza'),
  ('C06', 'CC-860 CIRUELOS ADULTOS', 'D''Agen', 'ciruela'),
  ('C07', '882 Rainier 2015', 'Rainier', 'cereza'),
  ('C08', '894 IVU 115', 'IVU 115', 'cereza'),
  ('C09', '862 Santina 2020 Norte', 'Santina', 'cereza'),
  ('C10', '863 Santina 2020 Sur', 'Santina', 'cereza'),
  ('C11', '864 Santina 2019 Norte', 'Santina', 'cereza'),
  ('C12', '865 Santina 2019 Sur', 'Santina', 'cereza'),
  ('C16', '866 CEREZOS 2024', 'Cerezas', 'cereza');

-- Clave de arranque. Cambiarla antes de usar la app.
INSERT INTO cosecha_app_usuarios (usuarioid, usuario, "contraseña", rol)
VALUES (
  '2b8c63f3-0a6d-4318-9465-273d294e4d55',
  'admin',
  'cambiar-esta-clave',
  'admin'
);

COMMIT;
