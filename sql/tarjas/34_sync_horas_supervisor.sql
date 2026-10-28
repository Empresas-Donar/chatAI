-- =============================================================================
-- TARJAS: al cambiar las horas en la tarja del supervisor, recalcular el pago
--
-- AppSheet edita horas_trabajadas en tarjas_supervisor (texto, "7.5" o "7,5").
-- El monto vive en tarjas_pagos. trg_fix_total_jornada ya escuchaba
-- horas_trabajadas ahí, pero el edit del supervisor no tocaba esa fila, así
-- que el valor no se movía.
--
-- Este script:
--   1. Redondea la jornada al día y escala el recargo del contratista en la
--      misma proporción, solo cuando todavía calza con el total viejo.
--   2. Copia las horas del supervisor a los pagos de esa tarja.
--   3. Corrige las filas Pendiente que ya quedaron en 75 h con la hora real
--      (el caso 21/10, $220.000). No toca días ya aprobados ni tarifas que
--      AppSheet ya había dividido por diez.
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION appsheet.fix_total_jornada_bug()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_old NUMERIC;
    v_correct NUMERIC;
BEGIN
    IF lower(NEW.tipo_pago) IN ('al dia', 'al día') THEN
        v_old := COALESCE(NEW.total_jornada, 0);
        v_correct := ROUND(
            COALESCE(NEW.valor_jornada, 0) * COALESCE(NEW.horas_trabajadas, 0)
            + COALESCE(NEW.total_hora_extra, 0),
            0
        );
        IF ABS(v_old - v_correct) > 500 THEN
            -- El recargo al día es la mitad del total. Si AppSheet reescribe
            -- solo el total y el recargo ya quedó a escala, no se vuelve a partir.
            IF v_old <> 0
               AND ABS(COALESCE(NEW.total_contratista, 0) - ROUND(v_old * 0.5, 0)) <= 1 THEN
                NEW.total_contratista := ROUND(NEW.total_contratista * v_correct / v_old, 0);
            END IF;
            IF v_old <> 0
               AND ABS(COALESCE(NEW.contratista_jornada, 0) - ROUND(v_old * 0.5, 0)) <= 1 THEN
                NEW.contratista_jornada := ROUND(NEW.contratista_jornada * v_correct / v_old, 0);
            END IF;
            NEW.total_jornada := v_correct;
            NEW.total_trabajado := v_correct + COALESCE(NEW.total_trato, 0);
            IF COALESCE(NEW.total_pagar, 0) <> 0 THEN
                NEW.total_pagar := NEW.total_trabajado + COALESCE(NEW.total_contratista, 0);
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_fix_total_jornada ON appsheet.tarjas_pagos;

CREATE TRIGGER trg_fix_total_jornada
BEFORE INSERT OR UPDATE OF valor_jornada, horas_trabajadas, total_hora_extra,
                           tipo_pago, total_jornada, total_trabajado,
                           total_contratista, contratista_jornada, total_pagar
ON appsheet.tarjas_pagos
FOR EACH ROW EXECUTE FUNCTION appsheet.fix_total_jornada_bug();

CREATE OR REPLACE FUNCTION appsheet.sync_supervisor_hours_to_pagos()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_old NUMERIC;
    v_new NUMERIC;
BEGIN
    IF pg_trigger_depth() > 1 THEN
        RETURN NEW;
    END IF;
    IF NEW.horas_trabajadas IS NOT DISTINCT FROM OLD.horas_trabajadas THEN
        RETURN NEW;
    END IF;

    v_old := CASE
        WHEN REPLACE(TRIM(COALESCE(OLD.horas_trabajadas, '')), ',', '.')
             ~ '^[+-]?[0-9]+(\.[0-9]+)?$'
        THEN REPLACE(TRIM(OLD.horas_trabajadas), ',', '.')::numeric
    END;
    v_new := CASE
        WHEN REPLACE(TRIM(COALESCE(NEW.horas_trabajadas, '')), ',', '.')
             ~ '^[+-]?[0-9]+(\.[0-9]+)?$'
        THEN REPLACE(TRIM(NEW.horas_trabajadas), ',', '.')::numeric
    END;
    IF v_new IS NULL THEN
        RETURN NEW;
    END IF;

    -- Misma hora que la tarja, o la hora corrida por la coma (7,5 guardada
    -- como 75) cuando la tarifa sigue siendo la hora real (>= $1.000).
    UPDATE appsheet.tarjas_pagos p
       SET horas_trabajadas = v_new
      FROM appsheet.tarjas_det_supervisor d
     WHERE d.id_supervisor = NEW.id_supervisor
       AND p."id_Resumen" = d.id_detalle
       AND lower(TRIM(COALESCE(p.tipo_pago, ''))) IN ('al dia', 'al día')
       AND p.horas_trabajadas IS DISTINCT FROM v_new
       AND (
            p.horas_trabajadas IS NOT DISTINCT FROM v_old
            OR (
                v_old IS NOT NULL
                AND p.horas_trabajadas = v_old * 10
                AND COALESCE(p.valor_jornada, 0) >= 1000
            )
       );
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_sync_horas_supervisor ON appsheet.tarjas_supervisor;

CREATE TRIGGER trg_sync_horas_supervisor
AFTER UPDATE OF horas_trabajadas
ON appsheet.tarjas_supervisor
FOR EACH ROW
EXECUTE FUNCTION appsheet.sync_supervisor_hours_to_pagos();

COMMENT ON TRIGGER trg_sync_horas_supervisor ON appsheet.tarjas_supervisor IS
'Copia las horas editadas en la tarja del supervisor a los pagos Al día y deja que trg_fix_total_jornada recalcule el monto.';

-- Filas ya editadas: supervisor en 7.5 y el pago todavía en 75 h × tarifa real.
UPDATE appsheet.tarjas_pagos p
   SET horas_trabajadas = REPLACE(TRIM(s.horas_trabajadas), ',', '.')::numeric
  FROM appsheet.tarjas_det_supervisor d
  JOIN appsheet.tarjas_supervisor s ON s.id_supervisor = d.id_supervisor
 WHERE p."id_Resumen" = d.id_detalle
   AND p.estado = 'Pendiente'
   AND lower(TRIM(COALESCE(p.tipo_pago, ''))) IN ('al dia', 'al día')
   AND COALESCE(p.valor_jornada, 0) >= 1000
   AND REPLACE(TRIM(COALESCE(s.horas_trabajadas, '')), ',', '.') ~ '^[0-9]+(\.[0-9]+)?$'
   AND p.horas_trabajadas = REPLACE(TRIM(s.horas_trabajadas), ',', '.')::numeric * 10
   AND ABS(
        COALESCE(p.total_jornada, 0)
        - ROUND(p.valor_jornada * p.horas_trabajadas, 0)
   ) <= 500;

COMMIT;
