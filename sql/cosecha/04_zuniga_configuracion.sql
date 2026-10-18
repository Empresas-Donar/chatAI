-- =============================================================================
-- Cosecha Zúñiga: configuración general de la app
--
-- OBSOLETO como fila ancha. La tabla quedó en key/value:
-- sql/cosecha/12_zuniga_configuracion_key_value.sql
--
-- Una sola fila, id_configuracion = 'general':
--   espera_activa    true  = se exige esperar entre capachos del mismo trabajador
--                    false = no se exige espera
--   espera_segundos  segundos de espera (la app usa 240 = 4 minutos)
--
-- Idempotente: no duplica la fila ni pisa valores que el admin ya cambió.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet;

CREATE TABLE IF NOT EXISTS cosecha_zuniga_configuracion (
  "id_configuracion" text      PRIMARY KEY,
  "espera_activa"    boolean   NOT NULL DEFAULT true,
  "espera_segundos"  integer   NOT NULL DEFAULT 240
                     CONSTRAINT cosecha_zuniga_configuracion_segundos_chk
                     CHECK ("espera_segundos" >= 0),
  "fecha_y_hora"     timestamp DEFAULT now()
);

INSERT INTO cosecha_zuniga_configuracion (
  "id_configuracion", "espera_activa", "espera_segundos"
)
VALUES ('general', true, 240)
ON CONFLICT ("id_configuracion") DO NOTHING;

-- Mismos privilegios que cosecha_zuniga_cuadrillas, para el usuario de AppSheet.
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT DISTINCT grantee, privilege_type
    FROM information_schema.role_table_grants
    WHERE table_schema = 'appsheet'
      AND table_name = 'cosecha_zuniga_cuadrillas'
  LOOP
    IF r.grantee = 'PUBLIC' THEN
      EXECUTE format(
        'GRANT %s ON appsheet.cosecha_zuniga_configuracion TO PUBLIC',
        r.privilege_type
      );
    ELSE
      EXECUTE format(
        'GRANT %s ON appsheet.cosecha_zuniga_configuracion TO %I',
        r.privilege_type, r.grantee
      );
    END IF;
  END LOOP;
END $$;

COMMIT;
