-- =============================================================================
-- TARJAS: Unificar MULTISERVICIOS BONHOMIA SPA con SERVICIOS AGRICOLAS PLP SPA.
--
-- El catálogo ya tenía el nombre nuevo como contratista vacío, duplicado en
-- Zúñiga. El historial (pagos, personas, plan diario) seguía en los ids viejos.
-- tarjas_pagos.contratista es texto libre: el rename del catálogo no se propaga.
--
-- Se conserva un id por predio, el PLP cuya jornada coincide con Bonhomía
-- ($18.000). Se descarta el PLP de Zúñiga con jornada $15.000, que no tenía
-- personas ni planes.
--
--   Zúñiga    d14ab196 -> 1576acaa
--   Kontrolag 4a12bd12 -> 4a10bd10
--   se elimina c403e047 (Zúñiga, jornada 15.000, sin hijos)
--
-- tarjas_reporte y las vistas Odoo leen tarjas_pagos: se actualizan solas.
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_personal
SET id_contratista = '1576acaa'
WHERE id_contratista = 'd14ab196';

UPDATE appsheet.tarjas_personal
SET id_contratista = '4a10bd10'
WHERE id_contratista = '4a12bd12';

UPDATE appsheet.tarjas_plan_diario
SET id_contratista = '1576acaa'
WHERE id_contratista = 'd14ab196';

UPDATE appsheet.tarjas_plan_diario
SET id_contratista = '4a10bd10'
WHERE id_contratista = '4a12bd12';

UPDATE appsheet.tarjas_pagos
SET contratista = 'SERVICIOS AGRICOLAS PLP SPA'
WHERE contratista = 'MULTISERVICIOS BONHOMIA SPA';

UPDATE appsheet.tarjas_bono_mensual
SET contratista = 'SERVICIOS AGRICOLAS PLP SPA'
WHERE contratista = 'MULTISERVICIOS BONHOMIA SPA';

DELETE FROM appsheet.tarjas_contratistas
WHERE id_contratista IN ('d14ab196', '4a12bd12', 'c403e047');

COMMIT;
