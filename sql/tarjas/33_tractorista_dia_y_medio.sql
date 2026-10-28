-- =============================================================================
-- TARJAS: un día y medio de tractorista se paga completo
--
-- Gabriel Necupil, 15/10/2026, Zúñiga, CC 890, tractor RLXJ64:
-- jornada de 9 h ($72.000) y media jornada de 4,5 h ($36.000).
--
-- La misma labor con las mismas horas, el mismo día, cuartel y tractor,
-- sigue quedándose con el último registro. Horas distintas se pagan las dos.
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION appsheet.aplicar_costo_tractorista()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_fecha DATE;
    v_costo NUMERIC;
    v_manual NUMERIC;
    v_cuando TIMESTAMPTZ;
BEGIN
    -- El UPDATE que deja en 0 al registro anterior vuelve a entrar acá.
    IF pg_trigger_depth() > 1 THEN
        RETURN NEW;
    END IF;

    IF lower(trim(COALESCE(NEW.tipo_pago, ''))) IS DISTINCT FROM 'tractorista' THEN
        RETURN NEW;
    END IF;

    -- Bono mensual de un tractorista: el monto lo escribe el fanout.
    -- No se reemplaza por la tarifa de la jornada.
    IF lower(trim(COALESCE(NEW.labor, ''))) = 'bono mensual' THEN
        v_manual := COALESCE(
            NULLIF(NEW.total_pagar, 0),
            NULLIF(NEW.total_trabajado, 0),
            NULLIF(NEW.total_tractor, 0),
            0
        );
        NEW.total_tractor := v_manual;
        NEW.total_trabajado := v_manual;
        NEW.total_pagar := v_manual;
        RETURN NEW;
    END IF;

    -- Misma labor y las mismas horas, el mismo día, cuartel y tractor: es
    -- la misma jornada cargada dos veces. Cuenta el último registro.
    -- Horas distintas (un día y medio: 9 h y 4,5 h) se pagan las dos.
    -- No se rechaza la fila: la app tiene que poder guardarla.
    INSERT INTO appsheet.tarjas_tractorista_registro (id_resumen, registrado_en)
    VALUES (NEW."id_Resumen", clock_timestamp())
    ON CONFLICT (id_resumen) DO NOTHING;

    SELECT r.registrado_en
      INTO v_cuando
      FROM appsheet.tarjas_tractorista_registro r
     WHERE r.id_resumen = NEW."id_Resumen";

    IF EXISTS (
        SELECT 1
          FROM appsheet.tarjas_pagos p
          JOIN appsheet.tarjas_tractorista_registro r
            ON r.id_resumen = p."id_Resumen"
         WHERE p.trabajador IS NOT DISTINCT FROM NEW.trabajador
           AND split_part(COALESCE(p.fecha, ''), ' ', 1)
               IS NOT DISTINCT FROM split_part(COALESCE(NEW.fecha, ''), ' ', 1)
           AND p.nombre_campo IS NOT DISTINCT FROM NEW.nombre_campo
           AND COALESCE(trim(p.cuartel_cc), '') = COALESCE(trim(NEW.cuartel_cc), '')
           AND COALESCE(NULLIF(lower(trim(p.maquina)), ''), '')
               = COALESCE(NULLIF(lower(trim(NEW.maquina)), ''), '')
           AND p."id_Resumen" IS DISTINCT FROM NEW."id_Resumen"
           AND lower(trim(COALESCE(p.tipo_pago, ''))) = 'tractorista'
           AND lower(trim(COALESCE(p.labor, ''))) IS DISTINCT FROM 'bono mensual'
           AND p.labor IS NOT DISTINCT FROM NEW.labor
           AND p.horas_trabajadas IS NOT DISTINCT FROM NEW.horas_trabajadas
           AND r.registrado_en > v_cuando
    ) THEN
        NEW.total_tractor := 0;
        NEW.total_trabajado := 0;
        NEW.total_pagar := 0;
        RETURN NEW;
    END IF;

    UPDATE appsheet.tarjas_pagos p
       SET total_tractor = 0,
           total_trabajado = 0,
           total_pagar = 0
      FROM appsheet.tarjas_tractorista_registro r
     WHERE r.id_resumen = p."id_Resumen"
       AND p.trabajador IS NOT DISTINCT FROM NEW.trabajador
       AND split_part(COALESCE(p.fecha, ''), ' ', 1)
           IS NOT DISTINCT FROM split_part(COALESCE(NEW.fecha, ''), ' ', 1)
       AND p.nombre_campo IS NOT DISTINCT FROM NEW.nombre_campo
       AND COALESCE(trim(p.cuartel_cc), '') = COALESCE(trim(NEW.cuartel_cc), '')
       AND COALESCE(NULLIF(lower(trim(p.maquina)), ''), '')
           = COALESCE(NULLIF(lower(trim(NEW.maquina)), ''), '')
       AND p."id_Resumen" IS DISTINCT FROM NEW."id_Resumen"
       AND lower(trim(COALESCE(p.tipo_pago, ''))) = 'tractorista'
       AND lower(trim(COALESCE(p.labor, ''))) IS DISTINCT FROM 'bono mensual'
       AND p.labor IS NOT DISTINCT FROM NEW.labor
       AND p.horas_trabajadas IS NOT DISTINCT FROM NEW.horas_trabajadas
       AND r.registrado_en <= v_cuando
       AND (COALESCE(p.total_tractor, 0) <> 0
            OR COALESCE(p.total_trabajado, 0) <> 0
            OR COALESCE(p.total_pagar, 0) <> 0);

    -- AppSheet rewrites the whole row when the user edits the payment.
    -- If the day itself did not change, keep the amount they typed.
    IF TG_OP = 'UPDATE'
       AND NEW.fecha IS NOT DISTINCT FROM OLD.fecha
       AND NEW.trabajador IS NOT DISTINCT FROM OLD.trabajador
       AND NEW.labor IS NOT DISTINCT FROM OLD.labor
       AND NEW.horas_trabajadas IS NOT DISTINCT FROM OLD.horas_trabajadas
       AND lower(trim(COALESCE(NEW.tipo_pago, '')))
           IS NOT DISTINCT FROM lower(trim(COALESCE(OLD.tipo_pago, '')))
    THEN
        IF NEW.total_pagar IS DISTINCT FROM OLD.total_pagar THEN
            v_manual := NEW.total_pagar;
        ELSIF NEW.total_tractor IS DISTINCT FROM OLD.total_tractor THEN
            v_manual := NEW.total_tractor;
        ELSIF NEW.total_trabajado IS DISTINCT FROM OLD.total_trabajado THEN
            v_manual := NEW.total_trabajado;
        ELSE
            RETURN NEW;
        END IF;
        NEW.total_tractor := v_manual;
        NEW.total_trabajado := v_manual;
        NEW.total_pagar := v_manual;
        RETURN NEW;
    END IF;

    BEGIN
        v_fecha := TO_DATE(SPLIT_PART(NEW.fecha, ' ', 1), 'MM/DD/YYYY');
    EXCEPTION WHEN OTHERS THEN
        RETURN NEW;
    END;

    v_costo := appsheet.costo_tractorista(
        NEW.trabajador, NEW.labor, NEW.horas_trabajadas, v_fecha
    );
    IF v_costo IS NULL THEN
        RETURN NEW;
    END IF;

    NEW.total_tractor := v_costo;
    NEW.total_trabajado := v_costo;
    NEW.total_pagar := v_costo;
    RETURN NEW;
END;
$function$;

COMMENT ON FUNCTION appsheet.aplicar_costo_tractorista() IS
    'Trigger de tractorista: escribe el monto. La misma jornada repetida paga el último registro. Un día y una media jornada se pagan los dos.';

DROP TRIGGER IF EXISTS trg_costo_tractorista ON appsheet.tarjas_pagos;

CREATE TRIGGER trg_costo_tractorista
BEFORE INSERT OR UPDATE OF fecha, trabajador, labor, horas_trabajadas, tipo_pago,
    total_tractor, total_trabajado, total_pagar
ON appsheet.tarjas_pagos
FOR EACH ROW
WHEN (lower(trim(COALESCE(NEW.tipo_pago, ''))) = 'tractorista')
EXECUTE FUNCTION appsheet.aplicar_costo_tractorista();

COMMENT ON TRIGGER trg_costo_tractorista ON appsheet.tarjas_pagos IS
    'Activo solo si tipo_pago es Tractorista. No modifica trato, al día ni otras tarjas.';


UPDATE appsheet.tarjas_pagos
   SET horas_trabajadas = 9
 WHERE "id_Resumen" = 'a0599cf9'
   AND trabajador = 'Gabriel Necupil'
   AND fecha = '10/15/2026 00:00:00'
   AND horas_trabajadas IS DISTINCT FROM 9;

INSERT INTO appsheet.tarjas_pagos (
    "id_Resumen", id_supervisor, fecha, nombre_campo, cuartel_cc, labor,
    contratista, trabajador, tipo_pago, maquina, horas_trabajadas,
    horas_extras, total_tractor, estado
)
SELECT
    'b17ebda7', id_supervisor, fecha, nombre_campo, cuartel_cc, labor,
    contratista, trabajador, tipo_pago, maquina, 4.5,
    0, 0, 'Pendiente'
  FROM appsheet.tarjas_pagos
 WHERE "id_Resumen" = 'a0599cf9'
   AND NOT EXISTS (
       SELECT 1 FROM appsheet.tarjas_pagos WHERE "id_Resumen" = 'b17ebda7'
   );

COMMIT;
