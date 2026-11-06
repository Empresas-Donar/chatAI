-- =============================================================================
-- Cosecha app: el abandono se marca por día, no por bin
--
-- Misma regla que Zúñiga. El formulario manda id_trabajador_dia
-- (YYYY-MM-DD|id_cuadrilla|id_qr) y el lote trae id_campo.
-- Sigue aceptando id_registro-id_qr. La salida es una por persona, fecha y campo.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_app_salidas_lote
  ADD COLUMN IF NOT EXISTS id_contratista text;

COMMENT ON COLUMN cosecha_app_salidas_lote.id_contratista IS
  'Contratista que eligió el admin antes de la cuadrilla. No entra al cálculo del piso.';

COMMENT ON COLUMN cosecha_app_salidas_lote.trabajadores IS
  'EnumList. Cada valor es id_trabajador_dia (YYYY-MM-DD|id_cuadrilla|id_qr) o id_registro-id_qr.';

CREATE OR REPLACE FUNCTION cosecha_app_salidas_lote_expandir()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_clave     text;
  v_fecha     date;
  v_cuadrilla text;
  v_qr        text;
  v_reg       text;
  e           record;
BEGIN
  FOR v_clave IN
    SELECT btrim(x)
    FROM unnest(string_to_array(NEW.trabajadores, ',')) AS x
    WHERE btrim(x) <> ''
  LOOP
    IF v_clave LIKE '%|%|%' THEN
      v_fecha     := split_part(v_clave, '|', 1)::date;
      v_cuadrilla := split_part(v_clave, '|', 2);
      v_qr        := split_part(v_clave, '|', 3);
      v_reg       := NULL;
    ELSIF NEW.id_registro IS NOT NULL AND v_clave LIKE NEW.id_registro || '-%' THEN
      v_reg       := NEW.id_registro;
      v_qr        := substr(v_clave, length(NEW.id_registro) + 2);
      v_cuadrilla := NEW.id_cuadrilla;
      v_fecha     := NULL;
    ELSE
      RAISE EXCEPTION 'Clave de trabajador inválida: %', v_clave;
    END IF;

    SELECT es.trabajador,
           es.rut_trabajador,
           es.codigo_qr,
           COALESCE(es.fecha, es.fecha_y_hora::date) AS fecha,
           es.fecha_y_hora,
           COALESCE(b.id_trato, es.id_trato) AS id_trato,
           es.id_bins,
           es.cuadrilla
      INTO e
      FROM cosecha_app_escaneo es
      LEFT JOIN cosecha_app_bins b ON b.id_bins = es.id_bins
     WHERE es.id_qr = v_qr
       AND es.id_campo = NEW.id_campo
       AND (
             (v_reg IS NOT NULL AND es.id_registro = v_reg)
          OR (v_reg IS NULL
              AND COALESCE(es.fecha, es.fecha_y_hora::date) = v_fecha
              AND es.id_cuadrilla = v_cuadrilla)
           )
     ORDER BY es.fecha_y_hora DESC
     LIMIT 1;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'El trabajador % no tiene capachos ese día en esa cuadrilla', v_qr;
    END IF;

    v_fecha := COALESCE(v_fecha, e.fecha);

    DELETE FROM cosecha_app_salidas_trabajador
     WHERE id_qr = v_qr
       AND fecha = v_fecha
       AND id_campo = NEW.id_campo;

    INSERT INTO cosecha_app_salidas_trabajador (
      id_salida, fecha, id_qr, trabajador, rut, codigo_qr, accion_piso,
      comentario, hora_salida, registrado_por, id_bins, id_trato, id_campo, created_at
    ) VALUES (
      'salida-' || NEW.id_campo || '-' || to_char(v_fecha, 'YYYYMMDD') || '-' || v_qr,
      v_fecha,
      v_qr,
      e.trabajador,
      e.rut_trabajador,
      e.codigo_qr,
      NEW.accion_piso,
      'abandono ' || COALESCE(e.cuadrilla::int::text, '')
        || COALESCE(' - ' || NULLIF(btrim(NEW.observacion), ''), ''),
      e.fecha_y_hora,
      NEW.registrado_por,
      e.id_bins,
      e.id_trato,
      NEW.id_campo,
      now()
    );
  END LOOP;

  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_salidas_lote_expandir ON cosecha_app_salidas_lote;
CREATE TRIGGER trg_salidas_lote_expandir
  AFTER INSERT ON cosecha_app_salidas_lote
  FOR EACH ROW EXECUTE FUNCTION cosecha_app_salidas_lote_expandir();

COMMIT;
