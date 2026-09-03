-- =============================================================================
-- TARJAS: Rellenar total_pagar cuando AppSheet lo deja en 0
-- Issue #156
--
-- total_pagar = total_trabajado + total_contratista (lo que paga la empresa).
-- Desde ~24/08/2026 AppSheet escribe total_pagar = 0 en filas nuevas aunque
-- las partes sí vienen llenas. El trigger trg_fix_total_jornada solo corrige
-- total_pagar cuando total_jornada está desfasado > $500, así que estas filas
-- (total_jornada correcto, total_pagar = 0) se cuelan.
--
-- Este script:
--   1. Extiende el trigger para rellenar total_pagar = partes cuando está en 0
--   2. Backfill de filas existentes (no Tractorista)
--   3. Recrea tarjas_reporte con el mismo fallback, por si AppSheet vuelve a
--      escribir 0 y el trigger no corre (UPDATE de otras columnas)
-- =============================================================================

BEGIN;

-- 1. Trigger: keep the jornada fix, then fill total_pagar when it is 0
CREATE OR REPLACE FUNCTION appsheet.fix_total_jornada_bug()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_correct NUMERIC;
    v_billable NUMERIC;
BEGIN
    IF lower(NEW.tipo_pago) IN ('al dia', 'al día') THEN
        v_correct := COALESCE(NEW.valor_jornada, 0) * COALESCE(NEW.horas_trabajadas, 0)
                     + COALESCE(NEW.total_hora_extra, 0);
        IF ABS(COALESCE(NEW.total_jornada, 0) - v_correct) > 500 THEN
            NEW.total_jornada := v_correct;
            NEW.total_trabajado := v_correct + COALESCE(NEW.total_trato, 0);
            NEW.total_pagar := (v_correct + COALESCE(NEW.total_trato, 0)) + COALESCE(NEW.total_contratista, 0);
        END IF;
    END IF;

    -- Issue #156: AppSheet left total_pagar at 0 while filling the parts.
    -- Tractorista bills via total_tractor; do not invent total_pagar there.
    IF lower(TRIM(COALESCE(NEW.tipo_pago, ''))) IS DISTINCT FROM 'tractorista'
       AND COALESCE(NEW.total_pagar, 0) = 0 THEN
        v_billable := COALESCE(NEW.total_trabajado, 0) + COALESCE(NEW.total_contratista, 0);
        IF v_billable > 0 THEN
            NEW.total_pagar := v_billable;
        END IF;
    END IF;

    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_fix_total_jornada ON appsheet.tarjas_pagos;

CREATE TRIGGER trg_fix_total_jornada
BEFORE INSERT OR UPDATE OF valor_jornada, horas_trabajadas, total_hora_extra,
                           tipo_pago, total_pagar, total_trabajado, total_contratista
ON appsheet.tarjas_pagos
FOR EACH ROW EXECUTE FUNCTION appsheet.fix_total_jornada_bug();

-- 2. Backfill stored zeros (same formula; skip Tractorista)
UPDATE appsheet.tarjas_pagos
SET total_pagar = COALESCE(total_trabajado, 0) + COALESCE(total_contratista, 0)
WHERE COALESCE(total_pagar, 0) = 0
  AND (COALESCE(total_trabajado, 0) + COALESCE(total_contratista, 0)) > 0
  AND lower(TRIM(COALESCE(tipo_pago, ''))) IS DISTINCT FROM 'tractorista';

-- 3. View fallback: same billable expression so reports stay correct even if
--    a future write bypasses the trigger column list.
CREATE OR REPLACE VIEW appsheet.tarjas_reporte AS
SELECT DISTINCT
    p.contratista,
    p.nombre_campo,
    p.fecha::DATE                                                           AS fecha,
    SUM(CASE WHEN LOWER(p.tipo_pago) = 'trato'
             THEN COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0))
             ELSE 0 END)
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_a_trato,
    SUM(CASE WHEN LOWER(p.tipo_pago) IN ('al dia', 'al día')
             THEN COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0))
             ELSE 0 END)
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_al_dia,
    SUM(COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0)))
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_a_pagar,
    ROUND(
        SUM(CASE WHEN LOWER(p.tipo_pago) = 'trato'
                 THEN COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0))
                 ELSE 0 END)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)::NUMERIC
        / NULLIF(SUM(COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0)))
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        1
    )                                                                       AS pct_trato,
    ROUND(
        SUM(CASE WHEN LOWER(p.tipo_pago) IN ('al dia', 'al día')
                 THEN COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0))
                 ELSE 0 END)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)::NUMERIC
        / NULLIF(SUM(COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0)))
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        1
    )                                                                       AS pct_al_dia,
    p.tipo_pago,
    p.cuartel_cc                                                            AS "CC",
    p.labor                                                                 AS "Nombre Labor",
    p.id_labor,
    COUNT(*) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS jornadas,
    ROUND(AVG(COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0))) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )::NUMERIC, 2)                                                          AS total_unitario,
    SUM(COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0))) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS total_labor,
    COALESCE(SUM(p.horas_trabajadas) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    ), 0)                                                                   AS horas_trabajadas,
    ROUND(
        SUM(COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0))) OVER (
            PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
        )::NUMERIC
        / NULLIF(SUM(COALESCE(NULLIF(p.total_pagar, 0), COALESCE(p.total_trabajado, 0) + COALESCE(p.total_contratista, 0)))
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        2
    )                                                                       AS "% Tipo de pago",
    COALESCE(SUM(p.horas_extras) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    ), 0)                                                                   AS horas_extras
FROM appsheet.tarjas_pagos p
WHERE p.estado = 'Aprobado'
ORDER BY
    p.fecha::DATE DESC,
    p.contratista,
    p.nombre_campo,
    p.tipo_pago,
    p.cuartel_cc;

COMMIT;
