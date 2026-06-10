-- =============================================================================
-- TARJAS: Vista reporte semanal por contratista
-- Reemplaza los reportes dinámicos de Google Sheets
-- total_pagar = total_trabajado + total_contratista (lo que paga la empresa)
-- =============================================================================
CREATE OR REPLACE VIEW appsheet.tarjas_reporte AS
SELECT DISTINCT
    -- Cabecera
    p.contratista,
    p.nombre_campo,
    p.fecha::DATE                                                           AS fecha,
    SUM(CASE WHEN LOWER(p.tipo_pago) = 'trato'
             THEN p.total_pagar ELSE 0 END)
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_a_trato,
    SUM(CASE WHEN LOWER(p.tipo_pago) IN ('al dia', 'al día')
             THEN p.total_pagar ELSE 0 END)
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_al_dia,
    SUM(p.total_pagar)
        OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)   AS total_a_pagar,
    ROUND(
        SUM(CASE WHEN LOWER(p.tipo_pago) = 'trato'
                 THEN p.total_pagar ELSE 0 END)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)::NUMERIC
        / NULLIF(SUM(p.total_pagar)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        1
    )                                                                       AS pct_trato,
    ROUND(
        SUM(CASE WHEN LOWER(p.tipo_pago) IN ('al dia', 'al día')
                 THEN p.total_pagar ELSE 0 END)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE)::NUMERIC
        / NULLIF(SUM(p.total_pagar)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        1
    )                                                                       AS pct_al_dia,

    -- Detalle por labor
    p.tipo_pago,
    p.cuartel_cc                                                            AS "CC",
    p.labor                                                                 AS "Nombre Labor",
    COUNT(*) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS jornadas,
    ROUND(AVG(p.total_pagar) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )::NUMERIC, 2)                                                          AS total_unitario,
    SUM(p.total_pagar) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS total_labor,
    ROUND(
        SUM(p.total_pagar) OVER (
            PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
        )::NUMERIC
        / NULLIF(SUM(p.total_pagar)
            OVER (PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE), 0) * 100,
        2
    )                                                                       AS "% Tipo de pago"

FROM appsheet.tarjas_pagos p
WHERE p.estado = 'Aprobado'
ORDER BY
    p.fecha::DATE DESC,
    p.contratista,
    p.nombre_campo,
    p.tipo_pago,
    p.cuartel_cc;
