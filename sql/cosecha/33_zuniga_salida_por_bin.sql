-- =============================================================================
-- Cosecha Zúñiga: la salida queda amarrada al bin, no a la fecha
--
-- El formulario manda id de Resumen Bin: "<id_registro>-<id_qr>".
-- Sigue aceptando la clave vieja "fecha|id_cuadrilla|id_qr".
-- Una fila de cosecha_zuniga_salidas_trabajador es un trabajador en un bin.
-- El piso de ese bin es accion_piso. Los otros bins no se tocan.
--
-- Las salidas ya cargadas (29/10) eran una decisión del día. Se copian a
-- cada bin que esa persona escaneó ese día, para que el piso no vuelva.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

-- El único trigger de la tabla es trg_salidas_lote_expandir. Si aparece
-- otro, se borra para que un lote no inserte dos veces.
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT tgname
    FROM pg_trigger
    WHERE tgrelid = 'appsheet.cosecha_zuniga_salidas_lote'::regclass
      AND NOT tgisinternal
      AND tgname <> 'trg_salidas_lote_expandir'
  LOOP
    EXECUTE format(
      'DROP TRIGGER IF EXISTS %I ON appsheet.cosecha_zuniga_salidas_lote',
      r.tgname
    );
  END LOOP;
END $$;

ALTER TABLE cosecha_zuniga_salidas_trabajador
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_salidas_fecha_qr;

ALTER TABLE cosecha_zuniga_salidas_trabajador
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_salidas_bins_qr;

ALTER TABLE cosecha_zuniga_salidas_trabajador
  ADD CONSTRAINT cosecha_zuniga_salidas_bins_qr UNIQUE (id_bins, id_qr);

-- La decisión del 29/10 cubre cada bin de ese día, no solo el que quedó
-- anotado en la fila original.
INSERT INTO cosecha_zuniga_salidas_trabajador (
  id_salida, fecha, id_qr, trabajador, rut, codigo_qr, accion_piso,
  comentario, hora_salida, registrado_por, id_bins, id_trato, created_at
)
SELECT
  'salida-' || b.id_bins || '-' || s.id_qr,
  s.fecha,
  s.id_qr,
  s.trabajador,
  s.rut,
  s.codigo_qr,
  s.accion_piso,
  s.comentario,
  b.hora_salida,
  s.registrado_por,
  b.id_bins,
  b.id_trato,
  s.created_at
FROM cosecha_zuniga_salidas_trabajador s
JOIN (
  SELECT
    e.id_qr,
    COALESCE(e.fecha, e.fecha_y_hora::date) AS fecha,
    e.id_bins,
    max(e.fecha_y_hora) AS hora_salida,
    (array_agg(COALESCE(bin.id_trato, e.id_trato) ORDER BY e.fecha_y_hora DESC))[1] AS id_trato
  FROM cosecha_zuniga_escaneo e
  LEFT JOIN cosecha_zuniga_bins bin ON bin.id_bins = e.id_bins
  WHERE e.id_bins IS NOT NULL
    AND e.fecha_y_hora IS NOT NULL
  GROUP BY 1, 2, 3
) b
  ON b.id_qr = s.id_qr
 AND b.fecha = s.fecha
 AND b.id_bins IS DISTINCT FROM s.id_bins
ON CONFLICT ON CONSTRAINT cosecha_zuniga_salidas_bins_qr DO NOTHING;

CREATE OR REPLACE FUNCTION fn_salidas_lote_expandir()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  k           text;
  v_id_qr     text;
  v_bins      text;
  v_cuadrilla text;
  e           record;
BEGIN
  SELECT r.id_bins
    INTO v_bins
    FROM cosecha_zuniga_registro r
   WHERE r.id_registro = NEW.id_registro;

  IF v_bins IS NULL THEN
    RAISE EXCEPTION 'El registro % no tiene bin', NEW.id_registro;
  END IF;

  SELECT c.cuadrilla::text
    INTO v_cuadrilla
    FROM cosecha_zuniga_cuadrillas c
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

    -- Último capacho de esa persona en este bin, sin mirar la fecha.
    SELECT es.trabajador,
           es.rut_trabajador,
           es.codigo_qr,
           es.fecha,
           es.fecha_y_hora,
           COALESCE(b.id_trato, es.id_trato) AS id_trato
      INTO e
      FROM cosecha_zuniga_escaneo es
      LEFT JOIN cosecha_zuniga_bins b ON b.id_bins = es.id_bins
     WHERE es.id_registro = NEW.id_registro
       AND es.id_qr = v_id_qr
     ORDER BY es.fecha_y_hora DESC
     LIMIT 1;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'No hay escaneos de % en el registro %', v_id_qr, NEW.id_registro;
    END IF;

    -- Una sola salida por trabajador y bin: se reemplaza la anterior.
    DELETE FROM cosecha_zuniga_salidas_trabajador
     WHERE id_qr = v_id_qr
       AND id_bins = v_bins;

    INSERT INTO cosecha_zuniga_salidas_trabajador (
      id_salida, fecha, id_qr, trabajador, rut, codigo_qr, accion_piso,
      comentario, hora_salida, registrado_por, id_bins, id_trato, created_at
    ) VALUES (
      'salida-' || v_bins || '-' || v_id_qr,
      COALESCE(e.fecha, e.fecha_y_hora::date, NEW.fecha),
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
END $$;

DROP TRIGGER IF EXISTS trg_salidas_lote_expandir ON cosecha_zuniga_salidas_lote;
CREATE TRIGGER trg_salidas_lote_expandir
  AFTER INSERT ON cosecha_zuniga_salidas_lote
  FOR EACH ROW EXECUTE FUNCTION fn_salidas_lote_expandir();

CREATE OR REPLACE VIEW cosecha_zuniga_resumen_bin_trabajador AS
WITH base AS (
  SELECT
    e.id_registro,
    e.id_qr,
    e.id_bins,
    COALESCE(e.fecha, e.fecha_y_hora::date) AS fecha,
    e.fecha_y_hora,
    COALESCE(e.precio_trato_aplicado::numeric, t.precio_capacho::numeric) AS precio,
    COALESCE(e.piso_aplicado::numeric, t.piso_garantizado_diario::numeric) AS piso_escaneo
  FROM cosecha_zuniga_escaneo e
  LEFT JOIN cosecha_zuniga_tratos t ON t.id_trato = e.id_trato
  WHERE e.id_registro IS NOT NULL
    AND e.id_qr IS NOT NULL
),
agg AS (
  SELECT
    id_registro,
    id_qr,
    max(id_bins) AS id_bins,
    count(*) AS capachos,
    max(precio) AS valor_trato,
    max(piso_escaneo) AS piso_escaneo,
    max(fecha_y_hora) AS ultimo,
    (array_agg(fecha ORDER BY fecha_y_hora DESC NULLS LAST))[1] AS fecha
  FROM base
  GROUP BY id_registro, id_qr
),
marcado AS (
  SELECT
    a.*,
    s.accion_piso,
    s.comentario
  FROM agg a
  LEFT JOIN cosecha_zuniga_salidas_trabajador s
    ON s.id_bins = a.id_bins
   AND s.id_qr = a.id_qr
)
SELECT
  id_registro || '-' || id_qr AS id_resumen,
  id_registro,
  id_qr,
  capachos,
  valor_trato,
  COALESCE(accion_piso, piso_escaneo) AS piso,
  capachos * valor_trato AS total_capachos,
  capachos * valor_trato + COALESCE(accion_piso, piso_escaneo, 0) AS total_a_recibir,
  CASE
    WHEN accion_piso IS NULL THEN NULL
    ELSE comentario
  END AS comentario
FROM marcado;

COMMENT ON TABLE cosecha_zuniga_salidas_trabajador IS
  'Reemplazo del piso de un trabajador en un bin. accion_piso es el monto que queda. Sin fila, ese bin paga el piso del escaneo.';

COMMENT ON COLUMN cosecha_zuniga_salidas_lote.trabajadores IS
  'EnumList. Cada valor es el id de Resumen Bin (id_registro-id_qr) o la clave vieja fecha|id_cuadrilla|id_qr.';

COMMENT ON VIEW cosecha_zuniga_resumen_bin_trabajador IS
  'Capachos, trato y piso por apertura de bin y trabajador. Si hay salida de ese bin, el piso es accion_piso. comentario dice por qué.';

COMMENT ON COLUMN cosecha_zuniga_resumen_bin_trabajador.comentario IS
  'Motivo guardado al modificar el piso de ese bin. Vacío si el piso es el del escaneo.';

COMMIT;
