-- =============================================================================
-- Cosecha Zúñiga: cuarteles Santina 2019 y 2020
--
-- Nombres y códigos salen de sql/tarjas/cc_nombres.csv (Zúñiga):
--   862 CEREZOS SANTINA 2020-NORTE
--   863 CEREZOS SANTINA 2020-SUR
--   864 CEREZOS SANTINA 2019-NORTE
--   865 CEREZOS SANTINA 2019-SUR
--
-- nombre_cuartel sigue el formato de los Santina que ya estaban
-- (por ejemplo "895 Santina 2018").
-- =============================================================================

BEGIN;

INSERT INTO appsheet.cosecha_zuniga_cuarteles (
  "id_cuartel", "nombre_cuartel", "variedad"
)
VALUES
  ('C09', '862 Santina 2020 Norte', 'Santina'),
  ('C10', '863 Santina 2020 Sur',   'Santina'),
  ('C11', '864 Santina 2019 Norte', 'Santina'),
  ('C12', '865 Santina 2019 Sur',   'Santina')
ON CONFLICT ("id_cuartel") DO UPDATE SET
  "nombre_cuartel" = EXCLUDED."nombre_cuartel",
  "variedad"       = EXCLUDED."variedad";

COMMIT;
