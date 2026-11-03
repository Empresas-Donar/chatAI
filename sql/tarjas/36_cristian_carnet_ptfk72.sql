-- =============================================================================
-- TARJAS: Cristian González, PTFK72, jornada con carnet desde el 27/10/2026
--
-- El tractor cumple los requerimientos. Desde esa fecha su jornada normal
-- lleva carnet: 7,5 h = 60.000 y 9 h = 72.000. Hasta el 26/10 sigue sin
-- carnet (7,5 h = 55.000, 9 h = 66.000). Horas extra y bono no cambian.
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_esquema_tractorista
   SET hasta = DATE '2026-10-26'
 WHERE id = 'cristian'
   AND trabajador = 'Cristian Gonzalez'
   AND desde = DATE '2026-01-01'
   AND (hasta IS NULL OR hasta > DATE '2026-10-26');

INSERT INTO appsheet.tarjas_esquema_tractorista
    (id, trabajador, desde, hasta, esquema, con_operador, carnet)
VALUES
    ('cristian-2026-10-27', 'Cristian Gonzalez', DATE '2026-10-27', NULL,
     'lun_vie', TRUE, TRUE)
ON CONFLICT (id) DO UPDATE SET
    trabajador = EXCLUDED.trabajador,
    desde = EXCLUDED.desde,
    hasta = EXCLUDED.hasta,
    esquema = EXCLUDED.esquema,
    con_operador = EXCLUDED.con_operador,
    carnet = EXCLUDED.carnet;

UPDATE appsheet.tarjas_pagos p
   SET total_tractor = c.costo,
       total_trabajado = c.costo,
       total_pagar = c.costo
  FROM (
        SELECT "id_Resumen",
               appsheet.costo_tractorista(
                   trabajador, labor, horas_trabajadas, fecha::date
               ) AS costo
          FROM appsheet.tarjas_pagos
         WHERE trabajador = 'Cristian Gonzalez'
           AND fecha::date >= DATE '2026-10-27'
           AND lower(trim(COALESCE(tipo_pago, ''))) = 'tractorista'
           AND lower(trim(COALESCE(labor, ''))) = 'jornada tractor normal'
           AND maquina ILIKE 'PTFK72%'
       ) c
 WHERE p."id_Resumen" = c."id_Resumen"
   AND c.costo IS NOT NULL
   AND (p.total_tractor IS DISTINCT FROM c.costo
        OR p.total_trabajado IS DISTINCT FROM c.costo
        OR p.total_pagar IS DISTINCT FROM c.costo);

COMMIT;
