-- =============================================================================
-- Cosecha Zúñiga: el abandono se marca por día, no por bin
--
-- El formulario manda id_trabajador_dia (YYYY-MM-DD|id_cuadrilla|id_qr).
-- Sigue aceptando id_registro-id_qr. La salida queda una por persona y fecha.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

ALTER TABLE cosecha_zuniga_salidas_lote
  ADD COLUMN IF NOT EXISTS id_contratista text;

COMMENT ON COLUMN cosecha_zuniga_salidas_lote.id_contratista IS
  'Contratista que eligió el admin antes de la cuadrilla. No entra al cálculo del piso.';

COMMENT ON COLUMN cosecha_zuniga_salidas_lote.trabajadores IS
  'EnumList. Cada valor es id_trabajador_dia (YYYY-MM-DD|id_cuadrilla|id_qr) o id_registro-id_qr.';

CREATE OR REPLACE FUNCTION fn_salidas_lote_expandir()
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

    SELECT s.* INTO e
    FROM cosecha_zuniga_escaneo s
    WHERE s.id_qr = v_qr
      AND (
            (v_reg IS NOT NULL AND s.id_registro = v_reg)
         OR (v_reg IS NULL AND s.fecha = v_fecha AND s.id_cuadrilla = v_cuadrilla)
          )
    ORDER BY s.fecha_y_hora DESC
    LIMIT 1;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'El trabajador % no tiene capachos ese día en esa cuadrilla', v_qr;
    END IF;

    v_fecha := COALESCE(v_fecha, e.fecha);

    DELETE FROM cosecha_zuniga_salidas_trabajador
    WHERE id_qr = v_qr
      AND fecha = v_fecha;

    INSERT INTO cosecha_zuniga_salidas_trabajador (
      id_salida, fecha, id_qr, accion_piso, comentario, hora_salida,
      registrado_por, id_bins, id_trato, created_at, trabajador, rut, codigo_qr
    ) VALUES (
      'salida-' || to_char(v_fecha, 'YYYYMMDD') || '-' || v_qr,
      v_fecha,
      v_qr,
      NEW.accion_piso,
      'abandono ' || COALESCE(e.cuadrilla::int::text, '')
        || COALESCE(' - ' || NULLIF(btrim(NEW.observacion), ''), ''),
      e.fecha_y_hora,
      NEW.registrado_por,
      e.id_bins,
      e.id_trato,
      now(),
      e.trabajador,
      e.rut_trabajador,
      e.codigo_qr
    );
  END LOOP;

  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_salidas_lote_expandir ON cosecha_zuniga_salidas_lote;
CREATE TRIGGER trg_salidas_lote_expandir
  AFTER INSERT ON cosecha_zuniga_salidas_lote
  FOR EACH ROW EXECUTE FUNCTION fn_salidas_lote_expandir();

COMMIT;
