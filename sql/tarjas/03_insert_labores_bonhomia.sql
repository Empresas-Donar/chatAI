-- =============================================================================
-- TARJAS: Insertar labores faltantes para KONTROLAG / BONHOMIA
-- Issue #32: "ENSAYOS Y PRUEBAS" y "MANTENCIÓN DE ESTRUCTURAS" no existían
-- en tarjas_labores, causando que todas las líneas de BONHOMIA/KONTROLAG
-- aparecieran como ⚠ Incompleta en la exportación a Odoo.
--
-- Códigos verificados contra Odoo BigQuery (odoo_data.Producto):
--   14.40 → "MANTENCIÓN DE ESTRUCTURAS " (product id 35780)
--   14.41 → "ENSAYOS Y PRUEBAS "         (product id 35781)
-- =============================================================================
INSERT INTO appsheet.tarjas_labores (codigo_labor, labor)
VALUES
    ('14.40', 'MANTENCIÓN DE ESTRUCTURAS'),
    ('14.41', 'ENSAYOS Y PRUEBAS')
ON CONFLICT DO NOTHING;
