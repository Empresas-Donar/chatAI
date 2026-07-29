-- =============================================================================
-- TARJAS: Vista reporte para importación a Odoo — solo Tractoristas
-- Análoga a tarjas_reporte_odoo pero para tipo_pago = 'Tractorista'.
--
-- Modelo de pago tractorista: tarifa diaria fija (total_tractor), no por hora.
-- horas_extras = 0 siempre → se usa jornadas (COUNT) como qty, igual que cuadrilla.
--
--   qty        → COUNT(*)        (número de jornadas/días por grupo)
--   price_unit → AVG(total_tractor)  (tarifa por jornada)
--
-- Estrategias de join para product_id (idénticas a tarjas_reporte_odoo):
--   l0 → id_labor numérico en tarjas_pagos (robusto, post-backfill issue #27)
--   l1 → nombre exacto normalizado (espacios múltiples colapsados) — fallback
--   l2 → prefijo [X.Y] en el nombre: "[2.1]AMARRA" → "2.1"             — fallback
--   l3 → prefijo X.Y- en el nombre:  "1.3-REPLANTE" → "1.3"            — fallback
-- =============================================================================
CREATE OR REPLACE VIEW appsheet.tarjas_reporte_odoo_tractorista AS
SELECT
    agg.contratista                                          AS "Vendedor",
    agg.labor                                                AS "Lineas del pedido/Producto/Nombre",
    agg.jornadas                                             AS "Lineas del pedido/Cantidad",
    agg.cuartel_cc                                           AS "Lineas del pedido/Código de Distribución Analítica/Código",
    agg.total_unitario                                       AS "Lineas del pedido/Precio un.",
    agg.contratista                                          AS "partner_id",

    -- order_line/product_id: l0 (id_labor directo) gana sobre los fallbacks de texto
    COALESCE(l0.codigo_labor, l1.codigo_labor, l2.codigo_labor, l3.codigo_labor) AS "order_line/product_id",
    agg.jornadas                                             AS "order_line/product_qty",
    (SELECT jsonb_object_agg(k, ROUND(v::numeric, 2))
     FROM jsonb_each_text(cc.valor_odoo) AS t(k,v))::text    AS "order_line/analytic_distribution",
    agg.total_unitario                                       AS "order_line/price_unit",

    -- campos de filtro (no se exportan, solo para WHERE en el endpoint)
    agg.fecha,
    agg.nombre_campo,
    agg.id_labor

FROM (
    SELECT
        p.contratista,
        p.nombre_campo,
        p.fecha::DATE                           AS fecha,
        p.cuartel_cc,
        p.labor,
        MIN(p.id_labor)                         AS id_labor,
        COUNT(*)                                AS jornadas,
        ROUND(AVG(p.total_tractor)::NUMERIC, 2) AS total_unitario
    FROM appsheet.tarjas_pagos p
    WHERE LOWER(TRIM(p.tipo_pago)) = 'tractorista'
    GROUP BY
        p.contratista,
        p.nombre_campo,
        p.fecha::DATE,
        p.cuartel_cc,
        p.labor
) agg

-- join l0: id_labor directo (robusto)
LEFT JOIN appsheet.tarjas_labores l0
       ON agg.id_labor IS NOT NULL
      AND l0.id_labor = agg.id_labor

-- join l1: nombre exacto, colapsando espacios múltiples y espacios adyacentes a paréntesis
LEFT JOIN appsheet.tarjas_labores l1
       ON agg.id_labor IS NULL
      AND TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(l1.labor), '\s+', ' ', 'g'), '\(\s+', '(', 'g'), '\s+\)', ')', 'g'))
        = TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(agg.labor), '\s+', ' ', 'g'), '\(\s+', '(', 'g'), '\s+\)', ')', 'g'))

-- join l2: prefijo [X.Y] en el nombre — ej. "[2.1]AMARRA" → "2.1"
LEFT JOIN appsheet.tarjas_labores l2
       ON agg.id_labor IS NULL
      AND agg.labor ~ '^\[[\d.]+\]'
      AND l2.codigo_labor = TRIM(SUBSTRING(agg.labor FROM '^\[([\d.]+)\]'))

-- join l3: prefijo X.Y- en el nombre — ej. "1.3-REPLANTE" → "1.3"
LEFT JOIN appsheet.tarjas_labores l3
       ON agg.id_labor IS NULL
      AND agg.labor ~ '^[\d]+\.[\d]+-'
      AND l3.codigo_labor = TRIM(SUBSTRING(agg.labor FROM '^([\d]+\.[\d]+)-'))

-- join a tarjas_cc para obtener distribución analítica Odoo (valor_odoo)
LEFT JOIN appsheet.tarjas_cc cc
       ON cc.id_cc::text = agg.cuartel_cc::text

ORDER BY agg.fecha DESC, agg.contratista, agg.cuartel_cc;
