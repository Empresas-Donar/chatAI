-- =============================================================================
-- TARJAS: Vista reporte para importación a Odoo
-- Columnas mapeadas a los campos de pedido de Odoo (order_line/*)
-- Fuentes:
--   tarjas_reporte   → datos de pago por labor/contratista/día
--   tarjas_labores   → código de producto Odoo (order_line/product_id)
--   tarjas_cc        → distribución analítica Odoo (valor_odoo JSONB) + cultivo de referencia
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
    COALESCE(l1.codigo_labor, l2.codigo_labor)           AS "order_line/product_id",
    r.jornadas                                           AS "order_line/product_qty",
    cc.valor_odoo::text                                  AS "order_line/analytic_distribution",
    r.total_unitario                                     AS "order_line/price_unit",

    -- campos para filtrar en consultas (no se exportan, solo para WHERE)
    r.fecha,
    r.nombre_campo,
    r.tipo_pago

FROM appsheet.tarjas_reporte r

-- join por nombre exacto
LEFT JOIN appsheet.tarjas_labores l1
       ON TRIM(LOWER(l1.labor)) = TRIM(LOWER(r."Nombre Labor"))

-- join por código extraído del prefijo [X.Y] en el nombre de labor
-- ej. "[2.1]AMARRA" → codigo_labor = "2.1"
LEFT JOIN appsheet.tarjas_labores l2
       ON r."Nombre Labor" ~ '^\[[\d.]+\]'
      AND l2.codigo_labor = TRIM(SUBSTRING(r."Nombre Labor" FROM '^\[([\d.]+)\]'))

-- join a tarjas_cc para obtener distribución analítica Odoo (valor_odoo)
LEFT JOIN appsheet.tarjas_cc cc
       ON cc.id_cc::text = r."CC"::text

-- excluir tractoristas (no generan línea de pedido de cuadrilla)
WHERE r.tipo_pago NOT IN ('Tractorista')

ORDER BY r.fecha DESC, r.contratista, r."CC";
