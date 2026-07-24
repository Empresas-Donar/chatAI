-- =============================================================================
-- Fix: Corregir tipos de dato numéricos en appsheet.tarjas_pagos
-- Issue #38
--
-- Las columnas horas_extras, rendimiento y horas_trabajadas tienen tipo TEXT
-- cuando deberían ser NUMERIC. Esto fuerza casting defensivo con regex en todo
-- el código Python y en las vistas SQL.
--
-- Verificado en producción: 0 valores no casteables en las tres columnas.
-- horas_trabajadas contiene decimales reales (6.5, 4.5, 2.5) → NUMERIC es correcto.
--
-- NOTA: La vista tarjas_reporte referencia horas_trabajadas, por lo que debe
-- ser descartada y recreada. tarjas_reporte_odoo depende de tarjas_reporte
-- y también debe ser recreada en cascada.
-- =============================================================================

BEGIN;

-- 1. Descartar las vistas que dependen de tarjas_pagos.horas_trabajadas
DROP VIEW IF EXISTS appsheet.tarjas_reporte_odoo;
DROP VIEW IF EXISTS appsheet.tarjas_reporte;

-- 2. Alterar los tipos de columna
ALTER TABLE appsheet.tarjas_pagos
    ALTER COLUMN "horas_extras"     TYPE NUMERIC USING "horas_extras"::NUMERIC,
    ALTER COLUMN "rendimiento"      TYPE NUMERIC USING "rendimiento"::NUMERIC,
    ALTER COLUMN "horas_trabajadas" TYPE NUMERIC USING "horas_trabajadas"::NUMERIC;

-- 3. Recrear tarjas_reporte sin el casting defensivo de regex
-- (las columnas ya son NUMERIC — SUM directo es suficiente)
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
    )                                                                       AS "% Tipo de pago"

FROM appsheet.tarjas_pagos p
WHERE p.estado = 'Aprobado'
ORDER BY
    p.fecha::DATE DESC,
    p.contratista,
    p.nombre_campo,
    p.tipo_pago,
    p.cuartel_cc;

-- 4. Recrear tarjas_reporte_odoo (sin cambios — solo necesita ser recreada por la cascada)
CREATE OR REPLACE VIEW appsheet.tarjas_reporte_odoo AS
SELECT
    r.contratista                                        AS "Vendedor",
    r."Nombre Labor"                                     AS "Lineas del pedido/Producto/Nombre",
    r.jornadas                                           AS "Lineas del pedido/Cantidad",
    r."CC"                                               AS "Lineas del pedido/Código de Distribución Analítica/Código",
    r.total_unitario                                     AS "Lineas del pedido/Precio un.",
    r.contratista                                        AS "partner_id",

    -- order_line/product_id: l0 (id_labor directo) gana sobre los fallbacks de texto
    COALESCE(l0.codigo_labor, l1.codigo_labor, l2.codigo_labor, l3.codigo_labor) AS "order_line/product_id",
    r.jornadas                                           AS "order_line/product_qty",
    (SELECT jsonb_object_agg(k, ROUND(v::numeric, 2))
     FROM jsonb_each_text(cc.valor_odoo) AS t(k,v))::text AS "order_line/analytic_distribution",
    r.total_unitario                                     AS "order_line/price_unit",

    -- campos para filtrar en consultas (no se exportan, solo para WHERE)
    r.fecha,
    r.nombre_campo,
    r.tipo_pago

FROM appsheet.tarjas_reporte r

-- join l0: id_labor directo (robusto) — resuelve sin comparar texto
LEFT JOIN appsheet.tarjas_labores l0
       ON r.id_labor IS NOT NULL
      AND l0.id_labor = r.id_labor

-- join l1: nombre exacto, colapsando espacios múltiples y espacios adyacentes a paréntesis
LEFT JOIN appsheet.tarjas_labores l1
       ON r.id_labor IS NULL
      AND TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(l1.labor), '\s+', ' ', 'g'), '\(\s+', '(', 'g'), '\s+\)', ')', 'g'))
        = TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(r."Nombre Labor"), '\s+', ' ', 'g'), '\(\s+', '(', 'g'), '\s+\)', ')', 'g'))

-- join l2: prefijo [X.Y] en el nombre — ej. "[2.1]AMARRA" → "2.1"
LEFT JOIN appsheet.tarjas_labores l2
       ON r.id_labor IS NULL
      AND r."Nombre Labor" ~ '^\[[\d.]+\]'
      AND l2.codigo_labor = TRIM(SUBSTRING(r."Nombre Labor" FROM '^\[([\d.]+)\]'))

-- join l3: prefijo X.Y- en el nombre — ej. "1.3-REPLANTE" → "1.3"
LEFT JOIN appsheet.tarjas_labores l3
       ON r.id_labor IS NULL
      AND r."Nombre Labor" ~ '^[\d]+\.[\d]+-'
      AND l3.codigo_labor = TRIM(SUBSTRING(r."Nombre Labor" FROM '^([\d]+\.[\d]+)-'))

-- join a tarjas_cc para obtener distribución analítica Odoo (valor_odoo)
LEFT JOIN appsheet.tarjas_cc cc
       ON cc.id_cc::text = r."CC"::text

-- excluir tractoristas (no generan línea de pedido de cuadrilla)
WHERE r.tipo_pago NOT IN ('Tractorista')

ORDER BY r.fecha DESC, r.contratista, r."CC";

COMMIT;

-- Verificación post-migración:
-- SELECT column_name, data_type
-- FROM information_schema.columns
-- WHERE table_schema = 'appsheet' AND table_name = 'tarjas_pagos'
--   AND column_name IN ('horas_extras', 'rendimiento', 'horas_trabajadas');
-- Debe devolver data_type = 'numeric' para las tres columnas.
