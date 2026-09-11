-- =============================================================================
-- TARJAS: Vista reporte semanal por contratista
-- Reemplaza los reportes dinámicos de Google Sheets
-- total_pagar = total_trabajado + total_contratista (lo que paga la empresa)
--
-- pagar_efectivo: desde ~2026-08-24 AppSheet deja total_pagar en 0 aunque
-- total_trabajado/total_contratista están correctos.  Usamos el mismo
-- fallback que la Orden de Facturación para que ambas superficies cuadren
-- y el export a Odoo tenga montos correctos (issue #156).
--
-- id_labor: algunos registros de la misma partición (contratista/campo/fecha/
-- tipo_pago/cc/labor) tienen id_labor distinto (NULL vs un valor).  Usar
-- MAX() OVER hace que todos los registros de la partición compartan el mismo
-- id_labor antes del DISTINCT, evitando la duplicación del total_labor.
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
    -- total_unitario_empresa: precio unitario Costo Empresa (issue #163).
    -- Must match tarjas_empresa.py: Trato ×1.45, Al Día ×1.50, resto ×1.0.
    -- Billed export still uses total_empresa() via costo_empresa_odoo_lines —
    -- do not treat this column as the billed source of truth.
    ROUND(AVG(
        p.total_trabajado * CASE
            WHEN LOWER(p.tipo_pago) = 'trato'             THEN 1.45
            WHEN LOWER(p.tipo_pago) IN ('al dia', 'al día') THEN 1.50
            ELSE 1.0
        END)
    ) OVER (
        PARTITION BY p.contratista, p.nombre_campo, p.fecha::DATE, p.tipo_pago, p.cuartel_cc, p.labor
    )::NUMERIC, 2)                                                          AS total_unitario_empresa,
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
