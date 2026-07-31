-- =============================================================================
-- TARJAS: Propagar el renombre de contratistas (hecho por el usuario en el
-- catálogo appsheet.tarjas_contratistas vía AppSheet) a los registros ya
-- ingresados en appsheet.tarjas_pagos.
-- Issue #75
--
-- tarjas_pagos.contratista es texto libre denormalizado, no una FK a
-- tarjas_contratistas — el rename del catálogo no se propaga solo.
--
-- Verificado antes de aplicar:
--   - 'RAMÓN DIAZ' (cualquier variante de mayúsculas via ILIKE): 69 filas,
--     todas tipo_pago='Tractorista'.
--   - 'Angel Celis' (cualquier variante): 0 filas — no-op hoy, se deja el
--     UPDATE igual por si existe con otra grafía no detectada, o para
--     futuros registros que aún no se hayan re-sincronizado.
--   - tarjas_reporte es una VIEW sobre tarjas_pagos — se actualiza sola,
--     sin acción adicional.
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_pagos
SET contratista = 'SERVICIOS AGRICOLAS RD SPA'
WHERE contratista ILIKE 'RAMÓN DIAZ' OR contratista ILIKE 'RAMON DIAZ';

UPDATE appsheet.tarjas_pagos
SET contratista = 'AGROSERVICIOS C Y G SPA'
WHERE contratista ILIKE 'ANGEL CELIS';

COMMIT;
