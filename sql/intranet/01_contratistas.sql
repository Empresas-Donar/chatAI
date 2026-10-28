-- Catálogo maestro de contratistas de la intranet.
--
-- No lo ve AppSheet: el esquema no es appsheet. Las apps siguen con su
-- nombre. El enlace id_intranet_contratistas es texto nullable, sin llave
-- foránea: borrar un maestro deja ese enlace en NULL y no borra filas.

CREATE SCHEMA IF NOT EXISTS intranet;

CREATE TABLE IF NOT EXISTS intranet.contratistas (
  id_intranet  TEXT PRIMARY KEY,
  nombre       TEXT NOT NULL,
  nombre_corto TEXT,
  rut          TEXT,
  activo       BOOLEAN NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT intranet_contratistas_nombre_nonempty CHECK (btrim(nombre) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_intranet_contratistas_nombre
  ON intranet.contratistas (lower(btrim(nombre)));

-- No agrega la columna si todavía se llama id_intranet: el rename lo hace
-- 02_enlace_suave.sql. Así un arranque no crea una segunda columna.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'appsheet'
      AND table_name = 'tarjas_contratistas'
      AND column_name IN ('id_intranet', 'id_intranet_contratistas')
  ) THEN
    ALTER TABLE appsheet.tarjas_contratistas
      ADD COLUMN id_intranet_contratistas TEXT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'appsheet'
      AND table_name = 'cosecha_zuniga_contratistas'
      AND column_name IN ('id_intranet', 'id_intranet_contratistas')
  ) THEN
    ALTER TABLE appsheet.cosecha_zuniga_contratistas
      ADD COLUMN id_intranet_contratistas TEXT;
  END IF;
END $$;

COMMENT ON TABLE intranet.contratistas IS
  'Maestro de contratistas de la intranet. No reemplaza los catálogos de AppSheet.';
