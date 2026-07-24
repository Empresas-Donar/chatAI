-- =============================================================================
-- TARJAS: Vista reporte para importación a Odoo
-- Columnas mapeadas a los campos de pedido de Odoo (order_line/*)
-- Mantiene granularidad diaria para que los filtros por fecha funcionen.
-- La consolidación por rango se hace en la query del endpoint.
-- Fuentes:
--   tarjas_reporte   → datos de pago por labor/contratista/día (solo Aprobado)
--   tarjas_labores   → código de producto Odoo (order_line/product_id)
--   tarjas_cc        → distribución analítica Odoo (valor_odoo JSONB)
--
-- Estrategias de join para product_id (en orden de prioridad):
--   l0 → id_labor numérico en tarjas_pagos (robusto, post-backfill issue #27)
--   l1 → nombre exacto normalizado (espacios múltiples colapsados) — fallback
--   l2 → prefijo [X.Y] en el nombre: "[2.1]AMARRA" → "2.1"             — fallback
--   l3 → prefijo X.Y- en el nombre:  "1.3-REPLANTE" → "1.3"            — fallback
-- =============================================================================
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
--   ej. "CONSTRUCCIÓN INFRAESTRUCTURA ( caminos...)" → "construcción infraestructura (caminos...)"
--   Fallback para filas con id_labor aún NULL
LEFT JOIN appsheet.tarjas_labores l1
       ON r.id_labor IS NULL
      AND TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(l1.labor), '\s+', ' ', 'g'), '\(\s+', '(', 'g'), '\s+\)', ')', 'g'))
        = TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(r."Nombre Labor"), '\s+', ' ', 'g'), '\(\s+', '(', 'g'), '\s+\)', ')', 'g'))

-- join l2: prefijo [X.Y] en el nombre — ej. "[2.1]AMARRA" → "2.1"
--   Fallback para filas con id_labor aún NULL
LEFT JOIN appsheet.tarjas_labores l2
       ON r.id_labor IS NULL
      AND r."Nombre Labor" ~ '^\[[\d.]+\]'
      AND l2.codigo_labor = TRIM(SUBSTRING(r."Nombre Labor" FROM '^\[([\d.]+)\]'))

-- join l3: prefijo X.Y- en el nombre — ej. "1.3-REPLANTE" → "1.3"
--   Fallback para filas con id_labor aún NULL
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
