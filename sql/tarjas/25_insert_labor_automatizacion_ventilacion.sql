-- =============================================================================
-- TARJAS: Insertar labor faltante "AUTOMATIZACIÓN VENTILACIÓN"
-- Issue #171: labor sin fila en tarjas_labores excluía las 41 jornadas de
-- MULTISERVICIOS BONHOMIA SPA / KONTROLAG (10 a 15 de septiembre de 2026)
-- del export a Odoo (⚠ Incompleta, order_line/product_id = NULL).
--
-- appsheet.tarjas_labor (catálogo AppSheet) ya tiene la fila:
--   id_labor = 14.39, nombre = 'AUTOMATIZACIÓN VENTILACIÓN'
-- El join de tarjas_reporte_odoo usa tarjas_labores, no tarjas_labor, y esa
-- fila nunca se copió. _sync_labores no puede auto-mapearla: BigQuery
-- odoo_data.Producto no trae este producto (mismo hueco que 14.25 / 14.46,
-- que sí exportan porque están en tarjas_labores).
--
-- codigo_labor = 14.39 es el id_labor de AppSheet, el mismo criterio que
-- 14.25 (REPARTIR…) y 14.46 (PREPARACION DE SUSTRATO) en esta OC.
-- =============================================================================
INSERT INTO appsheet.tarjas_labores (codigo_labor, labor)
VALUES
    ('14.39', 'AUTOMATIZACIÓN VENTILACIÓN')
ON CONFLICT DO NOTHING;
