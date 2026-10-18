-- =============================================================================
-- Cosecha Zúñiga: piso_garantizado_diario pasa de sí/no a pesos
--
-- La columna era boolean y AppSheet la mostraba como N / Y.
-- Pasa a numeric(12,0). Los true/false no traían monto: quedan NULL.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE TABLE IF NOT EXISTS bk_20261014_tratos AS
  SELECT * FROM cosecha_zuniga_tratos;

ALTER TABLE cosecha_zuniga_tratos
  ALTER COLUMN piso_garantizado_diario DROP DEFAULT,
  ALTER COLUMN piso_garantizado_diario TYPE numeric(12,0) USING NULL;

COMMENT ON COLUMN cosecha_zuniga_tratos.piso_garantizado_diario
  IS 'Valor mínimo diario garantizado por trabajador (CLP)';

COMMIT;
