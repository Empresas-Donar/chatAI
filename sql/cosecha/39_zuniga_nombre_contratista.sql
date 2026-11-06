-- Reemplaza el nombre mal escrito de la ficha de cosecha Zúñiga.
-- El enlace a intranet no cambia.

BEGIN;

UPDATE appsheet.cosecha_zuniga_contratistas
SET contratistas = 'PRESTACION DE SERVICIOS M Y D SPA'
WHERE id_contratista = 'f90ee4a5'
  AND contratistas IS DISTINCT FROM 'PRESTACION DE SERVICIOS M Y D SPA';

UPDATE appsheet.cosecha_zuniga_escaneo
SET contratista = 'PRESTACION DE SERVICIOS M Y D SPA'
WHERE id_contratista = 'f90ee4a5'
  AND contratista IS DISTINCT FROM 'PRESTACION DE SERVICIOS M Y D SPA';

COMMIT;
