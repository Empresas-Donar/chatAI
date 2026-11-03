-- =============================================================================
-- Cosecha Zúñiga: la salida cubre la fecha completa
--
-- El formulario sigue abriéndose desde un bin y manda id_registro-id_qr.
-- La fila que se guarda es una por persona y fecha. accion_piso reemplaza
-- el piso de todos los bins de ese día. Los capachos de cada bin se pagan.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

-- Queda una fila por persona y fecha. Si había una copia por bin, se
-- conserva la del último capacho.
DELETE FROM cosecha_zuniga_salidas_trabajador s
USING (
  SELECT id_salida,
         row_number() OVER (
           PARTITION BY fecha, id_qr
           ORDER BY hora_salida DESC, created_at DESC, id_salida DESC
         ) AS n
  FROM cosecha_zuniga_salidas_trabajador
) d
WHERE s.id_salida = d.id_salida
  AND d.n > 1;

ALTER TABLE cosecha_zuniga_salidas_trabajador
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_salidas_bins_qr;

ALTER TABLE cosecha_zuniga_salidas_trabajador
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_salidas_fecha_qr;

ALTER TABLE cosecha_zuniga_salidas_trabajador
  ADD CONSTRAINT cosecha_zuniga_salidas_fecha_qr UNIQUE (fecha, id_qr);

CREATE OR REPLACE FUNCTION fn_salidas_lote_expandir()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
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

    -- Nombre, hora y trato salen del bin que se marcó. La fecha cubre
    -- los demás bins del día.
    SELECT es.trabajador,
           es.rut_trabajador,
           es.codigo_qr,
           COALESCE(es.fecha, es.fecha_y_hora::date) AS fecha,
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

    v_fecha := e.fecha;

    DELETE FROM cosecha_zuniga_salidas_trabajador
     WHERE id_qr = v_id_qr
       AND fecha = v_fecha;

    INSERT INTO cosecha_zuniga_salidas_trabajador (
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
    s.comentario,
    row_number() OVER (
      PARTITION BY a.fecha, a.id_qr
      ORDER BY a.ultimo DESC NULLS LAST, a.id_registro DESC
    ) AS n
  FROM agg a
  LEFT JOIN cosecha_zuniga_salidas_trabajador s
    ON s.fecha = a.fecha
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
  capachos * valor_trato
    + CASE
        WHEN accion_piso IS NULL THEN COALESCE(piso_escaneo, 0)
        WHEN n = 1 THEN accion_piso
        ELSE 0
      END AS total_a_recibir,
  CASE
    WHEN accion_piso IS NULL THEN NULL
    ELSE comentario
  END AS comentario
FROM marcado;

COMMENT ON TABLE cosecha_zuniga_salidas_trabajador IS
  'Reemplazo del piso de un trabajador en una fecha. Vale para todos los bins de ese día. Sin fila, cada bin paga el piso del escaneo.';

COMMENT ON VIEW cosecha_zuniga_resumen_bin_trabajador IS
  'Capachos, trato y piso por bin. Si hay salida ese día, el piso de todos los bins es accion_piso y el monto entra una vez, en el bin del último capacho.';

COMMIT;
