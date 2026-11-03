-- =============================================================================
-- Cosecha Zúñiga: formulario de abandono
--
-- AppSheet guarda un lote (varios trabajadores, un piso, una observación).
-- El trigger abre una fila por persona y fecha en
-- cosecha_zuniga_salidas_trabajador, que es la tabla que usa el pago.
-- El monto cubre todos los bins de ese día.
-- No se crea cosecha_zuniga_salidas: sería otra tabla y el piso no cambiaría.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE TABLE IF NOT EXISTS cosecha_zuniga_salidas_lote (
  id_lote        text PRIMARY KEY,
  fecha          date NOT NULL,
  id_cuadrilla   text NOT NULL,
  id_registro    text,
  trabajadores   text NOT NULL,
  accion_piso    numeric NOT NULL CHECK (accion_piso >= 0),
  observacion    text,
  registrado_por text,
  created_at     timestamp NOT NULL DEFAULT now()
);

COMMENT ON TABLE cosecha_zuniga_salidas_lote IS
  'Formulario de abandono. Una fila es un lote: varios trabajadores, un piso, una observación.';

COMMENT ON COLUMN cosecha_zuniga_salidas_lote.trabajadores IS
  'EnumList. Cada valor es el id de Resumen Bin (id_registro-id_qr) o la clave vieja fecha|id_cuadrilla|id_qr.';

COMMENT ON COLUMN cosecha_zuniga_salidas_lote.accion_piso IS
  'Piso en CLP que escribe el supervisor. Reemplaza al piso del escaneo. 0 no paga piso.';

CREATE OR REPLACE VIEW cosecha_zuniga_trabajadores_dia AS
SELECT
  to_char(dia.fecha, 'YYYY-MM-DD') || '|' || dia.id_cuadrilla || '|' || dia.id_qr
                                                                   AS id_trabajador_dia,
  dia.fecha,
  dia.id_cuadrilla,
  dia.id_qr,
  dia.trabajador,
  dia.rut,
  dia.trabajador || coalesce(' · ' || dia.rut, '')                 AS nombre_lista,
  dia.capachos,
  dia.ultimo_capacho
FROM (
  SELECT
    COALESCE(e.fecha, e.fecha_y_hora::date)                        AS fecha,
    e.id_cuadrilla,
    e.id_qr,
    max(e.trabajador)                                              AS trabajador,
    max(e.rut_trabajador)                                          AS rut,
    count(*)                                                       AS capachos,
    max(e.fecha_y_hora)                                            AS ultimo_capacho
  FROM cosecha_zuniga_escaneo e
  WHERE COALESCE(e.fecha, e.fecha_y_hora::date)
        >= (current_timestamp AT TIME ZONE 'America/Santiago')::date - 7
    AND e.id_qr IS NOT NULL
    AND e.id_cuadrilla IS NOT NULL
  GROUP BY 1, 2, 3
) dia;

COMMENT ON VIEW cosecha_zuniga_trabajadores_dia IS
  'Personas que escanearon en cada cuadrilla, últimos 7 días. La clave del EnumList es id_trabajador_dia.';

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
           es.id_bins,
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

COMMIT;
