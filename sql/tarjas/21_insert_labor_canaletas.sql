-- =============================================================================
-- TARJAS: Insertar labor faltante "CANALETAS AGUAS LLUVIA"
-- Issue #128: labor sin fila en tarjas_labores excluía las jornadas de
-- HERBI ML SPA / KONTROLAG (11 y 12 de agosto de 2026) del export a Odoo.
--
-- BigQuery odoo_data.Producto tiene el producto exacto:
--   "CANALETAS AGUAS LLUVIA" -> default_code = 14.42
-- El auto-sync (_sync_labores) solo corre cuando alguien genera el export/
-- preview para ese contratista+empresa+rango de fechas; nadie lo había
-- generado todavía, así que nunca se insertó automáticamente.
-- =============================================================================
INSERT INTO appsheet.tarjas_labores (codigo_labor, labor)
VALUES
    ('14.42', 'CANALETAS AGUAS LLUVIA')
ON CONFLICT DO NOTHING;
