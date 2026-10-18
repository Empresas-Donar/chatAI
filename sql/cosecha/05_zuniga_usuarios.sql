-- =============================================================================
-- Cosecha Zúñiga: reset de prueba y login por cuadrilla
--
-- Borra filas operativas de prueba. No toca:
--   cosecha_zuniga_configuracion  (fila general: espera entre capachos)
--   cosecha_zuniga_cuarteles      (catálogo del predio, no es prueba)
--   cosecha_zuniga_contratistas_bak
--
-- usuarios pasa a colgar de cuadrillas. Un acceso de rol cuadrilla exige
-- id_cuadrilla, y cada cuadrilla tiene como máximo un acceso.
-- El admin no lleva cuadrilla.
--
-- La clave del admin es un placeholder. Cambiarla después de aplicar.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet;

TRUNCATE TABLE
  cosecha_zuniga_escaneo,
  cosecha_zuniga_registro,
  cosecha_zuniga_qr,
  cosecha_zuniga_bins,
  cosecha_zuniga_cuadrillas,
  cosecha_zuniga_contratistas,
  cosecha_zuniga_tratos,
  cosecha_zuniga_filtros
RESTART IDENTITY CASCADE;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'cosecha_zuniga_cuadrillas'::regclass
      AND contype = 'p'
  ) THEN
    ALTER TABLE cosecha_zuniga_cuadrillas
      ADD CONSTRAINT cosecha_zuniga_cuadrillas_pkey
      PRIMARY KEY ("id_cuadrilla");
  END IF;
END $$;

DROP TABLE IF EXISTS cosecha_zuniga_usuarios CASCADE;

CREATE TABLE cosecha_zuniga_usuarios (
  "usuarioid"    text        PRIMARY KEY DEFAULT gen_random_uuid()::text,
  "usuario"      text        NOT NULL,
  "contraseña"   text        NOT NULL DEFAULT '1234',
  "rol"          text        NOT NULL DEFAULT 'cuadrilla'
                 CONSTRAINT cosecha_zuniga_usuarios_rol_chk
                 CHECK ("rol" IN ('admin', 'cuadrilla')),
  "id_cuadrilla" text        NULL
                 CONSTRAINT cosecha_zuniga_usuarios_cuadrilla_fk
                 REFERENCES cosecha_zuniga_cuadrillas ("id_cuadrilla")
                 ON DELETE CASCADE,
  "activo"       boolean     NOT NULL DEFAULT true,
  "creado_en"    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT cosecha_zuniga_usuarios_cuadrilla_chk
    CHECK ("rol" <> 'cuadrilla' OR "id_cuadrilla" IS NOT NULL)
);

-- Una cuadrilla = máximo un acceso.
CREATE UNIQUE INDEX cosecha_zuniga_usuarios_id_cuadrilla_uq
  ON cosecha_zuniga_usuarios ("id_cuadrilla")
  WHERE "id_cuadrilla" IS NOT NULL;

-- Login único, sin distinguir mayúsculas.
CREATE UNIQUE INDEX cosecha_zuniga_usuarios_usuario_uq
  ON cosecha_zuniga_usuarios (lower("usuario"));

COMMENT ON TABLE cosecha_zuniga_usuarios IS
  'Login de la app. admin no tiene cuadrilla; cuadrilla exige id_cuadrilla.';

COMMENT ON COLUMN cosecha_zuniga_usuarios."contraseña" IS
  'Secreto en texto plano. No seleccionarla, no loguearla, no exportarla.';

COMMENT ON COLUMN cosecha_zuniga_usuarios."id_cuadrilla" IS
  'Ref a cosecha_zuniga_cuadrillas. NULL solo si rol = admin.';

INSERT INTO cosecha_zuniga_usuarios ("usuario", "contraseña", "rol")
VALUES ('admin', 'cambiar-esta-clave', 'admin');

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
      AND grantee <> current_user
  LOOP
    IF r.grantee = 'PUBLIC' THEN
      EXECUTE format(
        'GRANT %s ON appsheet.cosecha_zuniga_usuarios TO PUBLIC',
        r.privilege_type
      );
    ELSE
      EXECUTE format(
        'GRANT %s ON appsheet.cosecha_zuniga_usuarios TO %I',
        r.privilege_type, r.grantee
      );
    END IF;
  END LOOP;
END $$;

COMMIT;
