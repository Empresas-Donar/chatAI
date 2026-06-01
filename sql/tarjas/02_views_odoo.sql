-- =============================================================================
-- TARJAS: Vista reporte para importación a Odoo
-- Columnas mapeadas a los campos de pedido de Odoo (order_line/*)
-- Fuentes:
--   tarjas_reporte   → datos de pago por labor/contratista/día (solo Aprobado)
--   tarjas_labores   → código de producto Odoo (order_line/product_id)
--   tarjas_cc        → distribución analítica Odoo (valor_odoo JSONB) + cultivo de referencia
--
-- Estrategias de join para product_id (en orden de prioridad):
--   l1 → nombre exacto normalizado (espacios múltiples colapsados)
--   l2 → prefijo [X.Y] en el nombre: "[2.1]AMARRA" → "2.1"
--   l3 → prefijo X.Y- en el nombre:  "1.3-REPLANTE" → "1.3"
-- =============================================================================
CREATE OR REPLACE VIEW appsheet.tarjas_reporte_odoo AS
SELECT
    r.contratista                                        AS "Vendedor",
    r."Nombre Labor"                                     AS "Lineas del pedido/Producto/Nombre",
    r.jornadas                                           AS "Lineas del pedido/Cantidad",
    r."CC"                                               AS "Lineas del pedido/Código de Distribución Analítica/Código",
    r.total_unitario                                     AS "Lineas del pedido/Precio un.",
    r.contratista                                        AS "partner_id",

    -- order_line/product_id: código de labor desde tarjas_labores
    COALESCE(l1.codigo_labor, l2.codigo_labor, l3.codigo_labor) AS "order_line/product_id",
    r.jornadas                                           AS "order_line/product_qty",
    (SELECT jsonb_object_agg(k, ROUND(v::numeric, 2))
     FROM jsonb_each_text(cc.valor_odoo) AS t(k,v))::text AS "order_line/analytic_distribution",
    r.total_unitario                                     AS "order_line/price_unit",

    -- campos para filtrar en consultas (no se exportan, solo para WHERE)
    r.fecha,
    r.nombre_campo,
    r.tipo_pago

FROM appsheet.tarjas_reporte r

-- join l1: nombre exacto, colapsando espacios múltiples
LEFT JOIN appsheet.tarjas_labores l1
       ON TRIM(REGEXP_REPLACE(LOWER(l1.labor), '\s+', ' ', 'g'))
        = TRIM(REGEXP_REPLACE(LOWER(r."Nombre Labor"), '\s+', ' ', 'g'))

-- join l2: prefijo [X.Y] en el nombre — ej. "[2.1]AMARRA" → "2.1"
LEFT JOIN appsheet.tarjas_labores l2
       ON r."Nombre Labor" ~ '^\[[\d.]+\]'
      AND l2.codigo_labor = TRIM(SUBSTRING(r."Nombre Labor" FROM '^\[([\d.]+)\]'))

-- join l3: prefijo X.Y- en el nombre — ej. "1.3-REPLANTE" → "1.3"
LEFT JOIN appsheet.tarjas_labores l3
       ON r."Nombre Labor" ~ '^[\d]+\.[\d]+-'
      AND l3.codigo_labor = TRIM(SUBSTRING(r."Nombre Labor" FROM '^([\d]+\.[\d]+)-'))

-- join a tarjas_cc para obtener distribución analítica Odoo (valor_odoo)
LEFT JOIN appsheet.tarjas_cc cc
       ON cc.id_cc::text = r."CC"::text

-- excluir tractoristas (no generan línea de pedido de cuadrilla)
WHERE r.tipo_pago NOT IN ('Tractorista')

ORDER BY r.fecha DESC, r.contratista, r."CC";
