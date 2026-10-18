-- =============================================================================
-- Cosecha Zúñiga: la cuadrilla ya no se relaciona con cuarteles
--
-- Se elimina cosecha_zuniga_cuadrilla_cuartel. El catálogo de cuarteles
-- sigue. El cuartel de un escaneo o de un registro es el lugar del capacho,
-- no una asignación de la cuadrilla.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

DO $$
BEGIN
  IF to_regclass('cosecha_zuniga_cuadrilla_cuartel') IS NULL THEN
    RETURN;
  END IF;

  IF to_regclass('bk_20261013_cuadrilla_cuartel') IS NULL THEN
    CREATE TABLE bk_20261013_cuadrilla_cuartel AS
    SELECT * FROM cosecha_zuniga_cuadrilla_cuartel;
  END IF;

  DROP TABLE cosecha_zuniga_cuadrilla_cuartel;
END $$;

COMMIT;
