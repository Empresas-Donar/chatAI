-- =============================================================================
-- Fix 1: tarjas_reporte usaba total_pagar directamente, pero desde ~2026-08-24
-- AppSheet deja total_pagar=0 en filas nuevas aunque total_trabajado y
-- total_contratista están correctos (issue #156).
--
-- Fix 2: SELECT DISTINCT duplicaba filas cuando dentro de la misma partición
-- (contratista/campo/fecha/tipo_pago/cc/labor) había registros con id_labor
-- diferente (NULL vs un valor). Esto inflaba total_labor en la Orden de Compra.
-- Solución: MAX(id_labor) OVER (partition) para unificar el valor antes del DISTINCT.
-- =============================================================================
CREATE OR REPLACE VIEW appsheet.tarjas_reporte AS
WITH raw AS (
    SELECT *,
        COALESCE(
            NULLIF(total_pagar, 0),
            COALESCE(total_trabajado, 0) + COALESCE(total_contratista, 0)
        ) AS pagar_efectivo
    FROM appsheet.tarjas_pagos
    WHERE estado = 'Aprobado'
)
SELECT DISTINCT
    -- Cabecera
    p.contratista,
    p.nombre_campo,
    p.fecha::DATE                                                           AS fecha,
    SUM(CASE WHEN LOWER(p.tipo_pago) = 'trato'
             THEN p.pagar_efectivo ELSE 0 END)
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_a_trato,
    SUM(CASE WHEN LOWER(p.tipo_pago) IN ('al dia', 'al día')
             THEN p.pagar_efectivo ELSE 0 END)
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_al_dia,
    SUM(p.pagar_efectivo)
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_a_pagar,
    ROUND(
        SUM(CASE WHEN LOWER(p.tipo_pago) = 'trato'
                 THEN p.pagar_efectivo ELSE 0 END)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)::NUMERIC
        / NULLIF(SUM(p.pagar_efectivo)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        1
    )                                                                       AS pct_trato,
    ROUND(
        SUM(CASE WHEN LOWER(p.tipo_pago) IN ('al dia', 'al día')
                 THEN p.pagar_efectivo ELSE 0 END)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)::NUMERIC
        / NULLIF(SUM(p.pagar_efectivo)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        1
    )                                                                       AS pct_al_dia,

    -- Detalle por labor
    p.tipo_pago,
    p.cuartel_cc                                                            AS "CC",
    p.labor                                                                 AS "Nombre Labor",
    -- MAX sobre la partición: si algunos registros tienen id_labor y otros NULL,
    -- todos quedan con el mismo valor antes del DISTINCT, evitando filas duplicadas.
    MAX(p.id_labor) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS id_labor,
    COUNT(*) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS jornadas,
    ROUND(AVG(p.pagar_efectivo) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )::NUMERIC, 2)                                                          AS total_unitario,
    SUM(p.pagar_efectivo) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS total_labor,
    COALESCE(SUM(p.horas_trabajadas) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    ), 0)                                                                   AS horas_trabajadas,
    ROUND(
        SUM(p.pagar_efectivo) OVER (
            PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
        )::NUMERIC
        / NULLIF(SUM(p.pagar_efectivo)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        2
    )                                                                       AS "% Tipo de pago",
    COALESCE(SUM(p.horas_extras) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    ), 0)                                                                   AS horas_extras

FROM raw p
ORDER BY
    p.fecha::DATE DESC,
    p.contratista,
    p.nombre_campo,
    p.tipo_pago,
    p.cuartel_cc;
