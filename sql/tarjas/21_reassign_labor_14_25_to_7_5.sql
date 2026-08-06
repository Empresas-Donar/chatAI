-- =============================================================================
-- TARJAS: Reasignar filas ingresadas con labor "14.25" (REPARTIR. ABRIR.
-- FLAMEAR. TENSAR. CLIPEAR Y FIJAR PLÁSTICO) al código de labor correcto
-- "7.5" (CONSTRUCCIÓN MACROTÚNELES).
-- Issue #86
--
-- appsheet.tarjas_pagos.id_labor / labor son texto libre (no FK a
-- tarjas_labores), así que la reasignación debe propagarse fila por fila.
--
-- Verificado antes de aplicar:
--   - appsheet.tarjas_labores tiene ambos códigos como labores distintas:
--     id 81 codigo_labor='14.25' ("REPARTIR. ABRIR. FLAMEAR. TENSAR.
--     CLIPEAR Y FIJAR PLÁSTICO") e id 36 codigo_labor='7.5' ("CONSTRUCCIÓN
--     MACROTÚNELES").
--   - appsheet.tarjas_pagos: 13 filas con id_labor='14.25', todas
--     nombre_campo='TALAGANTE', contratista='HERBI ML SPA',
--     tipo_pago='Al dia'.
--   - tarjas_reporte / tarjas_reporte_odoo son VIEWs sobre tarjas_pagos —
--     se actualizan solas, sin acción adicional. tarjas_reporte_odoo hace
--     match exacto id_labor -> tarjas_labores.id_labor (nivel 0 del
--     fallback de 4 niveles descrito en CLAUDE.md), así que el cambio de
--     id_labor basta para redirigir el codigo_labor exportado a Odoo.
--
-- Ya ejecutado directamente contra la BD de producción (2026-08-06).
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_pagos
SET id_labor = '7.5',
    labor = 'CONSTRUCCIÓN MACROTÚNELES'
WHERE id_labor = '14.25';

COMMIT;
