-- =============================================================================
-- Cosecha Zúñiga: configuración en key / value
--
-- Cada ajuste es una fila. El tope de cuadrillas se lee de la key
-- max_cuadrillas.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE TABLE cosecha_zuniga_configuracion_nueva (
  "key"   text PRIMARY KEY,
  "value" text NOT NULL,
  CONSTRAINT cosecha_zuniga_configuracion_valor_chk CHECK (
    ("key" = 'espera_activa' AND "value" IN ('true', 'false'))
    OR ("key" = 'espera_segundos' AND "value" ~ '^\d+$')
    OR ("key" = 'max_cuadrillas' AND "value" ~ '^[1-9][0-9]*$')
    OR "key" NOT IN ('espera_activa', 'espera_segundos', 'max_cuadrillas')
  )
);

INSERT INTO cosecha_zuniga_configuracion_nueva ("key", "value")
SELECT 'espera_activa', espera_activa::text
FROM cosecha_zuniga_configuracion
UNION ALL
SELECT 'espera_segundos', espera_segundos::text
FROM cosecha_zuniga_configuracion
UNION ALL
SELECT 'max_cuadrillas', max_cuadrillas::text
FROM cosecha_zuniga_configuracion;

DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT DISTINCT grantee, privilege_type
    FROM information_schema.role_table_grants
    WHERE table_schema = 'appsheet'
      AND table_name = 'cosecha_zuniga_configuracion'
      AND grantee <> current_user
  LOOP
    IF r.grantee = 'PUBLIC' THEN
      EXECUTE format(
        'GRANT %s ON appsheet.cosecha_zuniga_configuracion_nueva TO PUBLIC',
        r.privilege_type
      );
    ELSE
      EXECUTE format(
        'GRANT %s ON appsheet.cosecha_zuniga_configuracion_nueva TO %I',
        r.privilege_type, r.grantee
      );
    END IF;
  END LOOP;
END $$;

DROP TABLE cosecha_zuniga_configuracion;

ALTER TABLE cosecha_zuniga_configuracion_nueva
  RENAME TO cosecha_zuniga_configuracion;

ALTER TABLE cosecha_zuniga_configuracion
  RENAME CONSTRAINT cosecha_zuniga_configuracion_nueva_pkey
  TO cosecha_zuniga_configuracion_pkey;

COMMENT ON TABLE cosecha_zuniga_configuracion IS
  'Ajustes de la app. Una fila por key.';

COMMENT ON COLUMN cosecha_zuniga_configuracion."key" IS
  'Nombre del ajuste: espera_activa, espera_segundos, max_cuadrillas.';

COMMENT ON COLUMN cosecha_zuniga_configuracion."value" IS
  'Valor en texto. max_cuadrillas y espera_segundos son enteros.';

CREATE OR REPLACE FUNCTION cosecha_max_cuadrillas() RETURNS integer
LANGUAGE sql STABLE
SET search_path = appsheet, pg_catalog
AS $$
  SELECT COALESCE(
    (SELECT "value"::integer
     FROM cosecha_zuniga_configuracion
     WHERE "key" = 'max_cuadrillas'),
    16
  )
$$;

CREATE OR REPLACE FUNCTION cosecha_valida_max_cuadrillas()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_max int;
  v_bad bigint;
BEGIN
  v_max := cosecha_max_cuadrillas();

  SELECT MAX(x::bigint) INTO v_bad
  FROM regexp_split_to_table(COALESCE(NEW.cuadrillas, ''), '\s*,\s*') AS x
  WHERE x ~ '^\d+$'
    AND (x::bigint < 1 OR x::bigint > v_max);

  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'La cuadrilla % supera el máximo permitido (%)', v_bad, v_max;
  END IF;

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_valida_numero_cuadrilla()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_otra record;
  v_max int;
BEGIN
  IF current_setting('cosecha.syncing', true) = '1' THEN
    RETURN NEW;
  END IF;

  v_max := cosecha_max_cuadrillas();

  IF NEW.cuadrilla < 1 OR NEW.cuadrilla > v_max THEN
    RAISE EXCEPTION 'La cuadrilla % supera el máximo permitido (%)', NEW.cuadrilla, v_max;
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

COMMIT;
