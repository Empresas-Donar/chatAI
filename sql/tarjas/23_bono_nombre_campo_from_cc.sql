-- =============================================================================
-- TARJAS: Resolver nombre_campo en bonos mensuales
--
-- AppSheet a veces deja tarjas_bono_mensual.nombre_campo NULL, o manda el
-- id_campo ('3') en vez del nombre ('ZUÑIGA'). El fanout copiaba ese valor
-- tal cual a tarjas_pagos, así que el filtro Empresa de Detalle / Bonos
-- mensuales ocultaba los registros.
--
-- Este script:
--   1. Helper que resuelve nombre_campo (nombre real → id_campo → CC)
--   2. INSERT fanout usa el helper y lo persiste en ambas tablas
--   3. UPDATE fanout sincroniza la fila espejo en tarjas_pagos
--   4. Backfill de filas existentes con nombre_campo vacío o numérico
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION appsheet.resolve_bono_nombre_campo(
    p_nombre_campo TEXT,
    p_id_cc TEXT
) RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_campo TEXT;
BEGIN
    SELECT c.nombre INTO v_campo
    FROM appsheet.tarjas_campo c
    WHERE c.nombre = p_nombre_campo
    LIMIT 1;
    IF v_campo IS NOT NULL THEN
        RETURN v_campo;
    END IF;

    IF p_nombre_campo IS NOT NULL AND TRIM(p_nombre_campo) <> '' THEN
        SELECT c.nombre INTO v_campo
        FROM appsheet.tarjas_campo c
        WHERE c.id_campo::text = TRIM(p_nombre_campo)
        LIMIT 1;
        IF v_campo IS NOT NULL THEN
            RETURN v_campo;
        END IF;
    END IF;

    IF p_id_cc IS NOT NULL AND TRIM(p_id_cc) <> '' THEN
        SELECT c.nombre INTO v_campo
        FROM appsheet.tarjas_cc cc
        JOIN appsheet.tarjas_campo c ON c.id_campo = cc.id_campo
        WHERE cc.id_cc::text = TRIM(p_id_cc)
        LIMIT 1;
    END IF;

    RETURN v_campo;
END;
$$;


CREATE OR REPLACE FUNCTION appsheet.fanout_bono_mensual_insert()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_id_resumen TEXT;
BEGIN
    NEW.mes := date_trunc('month', NEW.mes)::date;
    NEW.nombre_campo := appsheet.resolve_bono_nombre_campo(NEW.nombre_campo, NEW.id_cc);
    v_id_resumen := substr(md5(random()::text || clock_timestamp()::text), 1, 8);

    INSERT INTO appsheet.tarjas_pagos (
        "id_Resumen",
        fecha,
        nombre_campo,
        cuartel_cc,
        labor,
        contratista,
        trabajador,
        rut_trabajador,
        tipo_pago,
        valor_jornada,
        valor_trato,
        base_trato,
        rendimiento,
        horas_extras,
        total_tractor,
        horas_trabajadas,
        total_hora_extra,
        total_jornada,
        total_trato,
        total_trabajado,
        contratista_jornada,
        contratista_trato,
        total_contratista,
        total_pagar,
        estado
    ) VALUES (
        v_id_resumen,
        to_char((NEW.mes + INTERVAL '1 month - 1 day')::date, 'MM/DD/YYYY') || ' 00:00:00',
        NEW.nombre_campo,
        NEW.id_cc,
        'Bono mensual',
        NEW.contratista,
        NEW.trabajador,
        NEW.rut_trabajador,
        'Bono',
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        NEW.monto,
        0,
        0,
        0,
        NEW.monto,
        COALESCE(NEW.estado, 'Pendiente')
    );

    NEW.id_resumen_pagos := v_id_resumen;
    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION appsheet.fanout_bono_mensual_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.mes := date_trunc('month', NEW.mes)::date;
    NEW.nombre_campo := appsheet.resolve_bono_nombre_campo(NEW.nombre_campo, NEW.id_cc);

    IF NEW.id_resumen_pagos IS NOT NULL THEN
        UPDATE appsheet.tarjas_pagos
        SET fecha          = to_char((NEW.mes + INTERVAL '1 month - 1 day')::date, 'MM/DD/YYYY') || ' 00:00:00',
            nombre_campo   = NEW.nombre_campo,
            cuartel_cc     = NEW.id_cc,
            contratista    = NEW.contratista,
            trabajador     = NEW.trabajador,
            rut_trabajador = NEW.rut_trabajador,
            total_trabajado = NEW.monto,
            total_pagar     = NEW.monto,
            estado          = CASE
                WHEN NEW.estado IS DISTINCT FROM OLD.estado
                THEN COALESCE(NEW.estado, estado)
                ELSE estado
            END
        WHERE "id_Resumen" = NEW.id_resumen_pagos;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_fanout_bono_mensual_update ON appsheet.tarjas_bono_mensual;

CREATE TRIGGER trg_fanout_bono_mensual_update
BEFORE UPDATE ON appsheet.tarjas_bono_mensual
FOR EACH ROW EXECUTE FUNCTION appsheet.fanout_bono_mensual_update();


UPDATE appsheet.tarjas_bono_mensual b
SET nombre_campo = appsheet.resolve_bono_nombre_campo(b.nombre_campo, b.id_cc)
WHERE appsheet.resolve_bono_nombre_campo(b.nombre_campo, b.id_cc) IS DISTINCT FROM b.nombre_campo;

UPDATE appsheet.tarjas_pagos p
SET nombre_campo = appsheet.resolve_bono_nombre_campo(p.nombre_campo, p.cuartel_cc)
WHERE p.labor = 'Bono mensual'
  AND appsheet.resolve_bono_nombre_campo(p.nombre_campo, p.cuartel_cc)
      IS DISTINCT FROM p.nombre_campo;

COMMIT;
