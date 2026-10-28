-- =============================================================================
-- TARJAS: Gabriel Necupil, 15/10/2026, Zúñiga, CC 890
--
-- La jornada es de 4,5 h. La fila de 9 h se corrige a media jornada.
-- La fila de 4,5 h que había quedado en $0 se elimina.
--
-- La regla de "quedarse con el último registro" está en
-- sql/tarjas/32_tractorista_ultimo_registro.sql. Acá no se rechaza la fila.
-- =============================================================================

BEGIN;

DELETE FROM appsheet.tarjas_pagos
 WHERE "id_Resumen" = 'b17ebda7'
   AND trabajador = 'Gabriel Necupil'
   AND fecha = '10/15/2026 00:00:00'
   AND COALESCE(total_tractor, 0) = 0;

UPDATE appsheet.tarjas_pagos
   SET horas_trabajadas = 4.5
 WHERE "id_Resumen" = 'a0599cf9'
   AND trabajador = 'Gabriel Necupil'
   AND fecha = '10/15/2026 00:00:00'
   AND horas_trabajadas IS DISTINCT FROM 4.5;

COMMIT;
