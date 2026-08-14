-- =============================================================================
-- TARJAS: Bonificaciones mensuales de trabajadores
-- Tabla nueva `tarjas_bono_mensual` para AppSheet (Add Table en el editor) +
-- triggers que reflejan cada bono como una fila en tarjas_pagos, reusando el
-- pipeline de reportes/export Odoo ya existente (tarjas_reporte,
-- tarjas_reporte_odoo) sin tocar esas vistas.
--
-- labor = 'Bono mensual' -> resuelve id_labor='6.10' vía el trigger existente
-- trg_set_id_labor (05_trigger_id_labor.sql), matchea por nombre de labor.
--
-- mes se normaliza siempre al día 1 del mes (evita duplicados por distinto
-- día-de-mes en la misma UNIQUE(trabajador, mes)); en tarjas_pagos.fecha se
-- exporta como el último día del mes.
-- =============================================================================

CREATE TABLE IF NOT EXISTS appsheet.tarjas_bono_mensual (
    id_bono           TEXT NOT NULL PRIMARY KEY
                       DEFAULT ('BM' || substr(md5(random()::text || clock_timestamp()::text), 1, 8)),
    trabajador        TEXT NOT NULL,
    rut_trabajador    TEXT,
    contratista       TEXT NOT NULL,
    nombre_campo      TEXT,
    id_cc             TEXT NOT NULL,
    mes               DATE NOT NULL,
    monto             NUMERIC NOT NULL,
    estado            TEXT NOT NULL DEFAULT 'Pendiente',
    id_resumen_pagos  TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_tarjas_bono_mensual_trabajador_mes UNIQUE (trabajador, mes)
);

-- -----------------------------------------------------------------------------
-- INSERT: normaliza mes al día 1, crea la fila espejo en tarjas_pagos y guarda
-- su id_Resumen en id_resumen_pagos para poder borrarla en cascada después.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION appsheet.fanout_bono_mensual_insert()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_id_resumen TEXT;
BEGIN
    NEW.mes := date_trunc('month', NEW.mes)::date;
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
        0,          -- valor_jornada
        0,          -- valor_trato
        0,          -- base_trato
        0,          -- rendimiento
        0,          -- horas_extras
        0,          -- total_tractor
        0,          -- horas_trabajadas
        0,          -- total_hora_extra
        0,          -- total_jornada
        0,          -- total_trato
        NEW.monto,  -- total_trabajado
        0,          -- contratista_jornada
        0,          -- contratista_trato
        0,          -- total_contratista
        NEW.monto,  -- total_pagar
        'Pendiente'
    );

    NEW.id_resumen_pagos := v_id_resumen;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_fanout_bono_mensual_insert ON appsheet.tarjas_bono_mensual;

CREATE TRIGGER trg_fanout_bono_mensual_insert
BEFORE INSERT ON appsheet.tarjas_bono_mensual
FOR EACH ROW EXECUTE FUNCTION appsheet.fanout_bono_mensual_insert();

-- -----------------------------------------------------------------------------
-- DELETE: si se borra el bono desde AppSheet, borra también su fila espejo
-- en tarjas_pagos para no dejar huérfanos en reportes/export.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION appsheet.fanout_bono_mensual_delete()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.id_resumen_pagos IS NOT NULL THEN
        DELETE FROM appsheet.tarjas_pagos WHERE "id_Resumen" = OLD.id_resumen_pagos;
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_fanout_bono_mensual_delete ON appsheet.tarjas_bono_mensual;

CREATE TRIGGER trg_fanout_bono_mensual_delete
AFTER DELETE ON appsheet.tarjas_bono_mensual
FOR EACH ROW EXECUTE FUNCTION appsheet.fanout_bono_mensual_delete();
