-- =============================================================================
-- TARJAS: Corregir nombre de contratista "MYD SPA" al nombre real del partner
-- en Odoo, "PRESTACION DE SERVICIOS M Y D SPA".
-- Issue #84
--
-- Se subió un Excel del intranet para este contratista (campo Zúñiga) hacia
-- Odoo y no fue reconocido: appsheet.tarjas_pagos.contratista es texto libre
-- denormalizado (no FK a tarjas_contratistas) y la vista tarjas_reporte_odoo
-- lo usa directamente como partner_id/Vendedor en el export — el nombre
-- corto no hace match con el partner real en Odoo.
--
-- Verificado antes de aplicar:
--   - appsheet.tarjas_contratistas: 1 fila, id_contratista='54SA6ASS4',
--     id_campo=3 (Zúñiga), nombre='MYD SPA'.
--   - appsheet.tarjas_pagos: 26 filas con contratista='MYD SPA', todas
--     nombre_campo='ZUÑIGA', tipo_pago='trato'.
--   - tarjas_reporte / tarjas_reporte_odoo son VIEWs sobre tarjas_pagos —
--     se actualizan solas, sin acción adicional.
--   - Sin coincidencias en tarjas_bono_mensual ni en las tablas de cosecha.
--
-- Ya ejecutado directamente contra la BD de producción (2026-08-06).
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_contratistas
SET nombre = 'PRESTACION DE SERVICIOS M Y D SPA'
WHERE id_contratista = '54SA6ASS4';

UPDATE appsheet.tarjas_pagos
SET contratista = 'PRESTACION DE SERVICIOS M Y D SPA'
WHERE contratista ILIKE 'MYD SPA';

COMMIT;
