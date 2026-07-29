-- =============================================================================
-- TARJAS: Vista reporte para importación a Odoo — solo Tractoristas
-- Análoga a tarjas_reporte_odoo pero para tipo_pago = 'Tractorista'.
--
-- Diferencias respecto a cuadrilla:
--   qty       → SUM(horas_extras)    (horas de maquinaria, no conteo de jornadas)
--   price_unit → SUM(total_tractor) / SUM(horas_extras)  (tarifa por hora)
--
-- Construida directamente desde tarjas_pagos para poder agregar horas_extras
-- sin necesidad de modificar la vista base tarjas_reporte.
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
    agg.horas_extras                                         AS "Lineas del pedido/Cantidad",
    agg.cuartel_cc                                           AS "Lineas del pedido/Código de Distribución Analítica/Código",
    CASE WHEN agg.horas_extras > 0
         THEN ROUND(agg.total_tractor / agg.horas_extras, 2)
         ELSE NULL END                                       AS "Lineas del pedido/Precio un.",
    agg.contratista                                          AS "partner_id",

    -- order_line/product_id: l0 (id_labor directo) gana sobre los fallbacks de texto
    COALESCE(l0.codigo_labor, l1.codigo_labor, l2.codigo_labor, l3.codigo_labor) AS "order_line/product_id",
    agg.horas_extras                                         AS "order_line/product_qty",
    (SELECT jsonb_object_agg(k, ROUND(v::numeric, 2))
     FROM jsonb_each_text(cc.valor_odoo) AS t(k,v))::text    AS "order_line/analytic_distribution",
    CASE WHEN agg.horas_extras > 0
         THEN ROUND(agg.total_tractor / agg.horas_extras, 2)
         ELSE NULL END                                       AS "order_line/price_unit",

    -- campos de filtro (no se exportan, solo para WHERE en el endpoint)
    agg.fecha,
    agg.nombre_campo,
    agg.id_labor

FROM (
    -- Agregación diaria por (contratista, nombre_campo, fecha, cuartel_cc, labor)
    -- Usa la misma lógica de partición que tarjas_reporte pero para tractoristas
    SELECT
        p.contratista,
        p.nombre_campo,
        p.fecha::DATE                           AS fecha,
        p.cuartel_cc,
        p.labor,
        -- id_labor: tomar el primero no nulo del grupo (todos deberían coincidir)
        MIN(p.id_labor)                         AS id_labor,
        SUM(p.horas_extras)                     AS horas_extras,
        SUM(p.total_tractor)                    AS total_tractor
    FROM appsheet.tarjas_pagos p
    WHERE p.estado = 'Aprobado'
      AND LOWER(TRIM(p.tipo_pago)) = 'tractorista'
      AND p.horas_extras IS NOT NULL
      AND p.horas_extras > 0
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
