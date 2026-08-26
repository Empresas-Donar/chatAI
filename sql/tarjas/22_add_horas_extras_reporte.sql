-- =============================================================================
-- TARJAS: agrega horas_extras a la vista tarjas_reporte
-- Necesario para que el reporte Detalle Operacional pueda calcular Costo/hora
-- en labores pagadas total o parcialmente como hora extra (horas_trabajadas=0
-- pero horas_extras>0) en vez de mostrar "-".
-- Columna agregada AL FINAL del SELECT: Postgres no permite insertar columnas
-- en medio de un CREATE OR REPLACE VIEW sin romper las posiciones existentes.
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
    p.id_labor,
    COUNT(*) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS jornadas,
    ROUND(AVG(p.total_pagar) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )::NUMERIC, 2)                                                          AS total_unitario,
    SUM(p.total_pagar) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )                                                                       AS total_labor,
    COALESCE(SUM(p.horas_trabajadas) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    ), 0)                                                                   AS horas_trabajadas,
    ROUND(
        SUM(p.total_pagar) OVER (
            PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
        )::NUMERIC
        / NULLIF(SUM(p.total_pagar)
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
