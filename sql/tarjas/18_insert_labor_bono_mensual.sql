-- =============================================================================
-- TARJAS: Insertar labor "Bono mensual" para bonificaciones mensuales
-- Issue: registro de bonificaciones mensuales de trabajadores dentro de tarjas.
--
-- Código verificado contra Odoo (referencia interna del producto):
--   6.10 → "Bono Mensual" (product id 35815)
--
-- Ya existe en AppSheet Labor (id_labor=11.13, nombre="Bono mensual"), pero ese
-- campo no se usa para el join real: el trigger trg_set_id_labor matchea por
-- nombre de labor (trim(labor) = trim(NEW.labor)), no por id_labor. El código
-- codigo_labor='6.10' es el que se exporta como order_line/product_id.
-- =============================================================================
INSERT INTO appsheet.tarjas_labores (codigo_labor, labor)
VALUES
    ('6.10', 'Bono mensual')
ON CONFLICT DO NOTHING;
