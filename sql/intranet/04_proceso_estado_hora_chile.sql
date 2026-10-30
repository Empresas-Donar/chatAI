-- Muestra revisado_en y enviado_en como hora de Chile, sin offset UTC.
-- Las filas ya guardadas se convierten una sola vez.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'intranet'
          AND table_name = 'proceso_estado'
          AND column_name = 'revisado_en'
          AND data_type = 'timestamp with time zone'
    ) THEN
        ALTER TABLE intranet.proceso_estado
            ALTER COLUMN "revisado_en" TYPE timestamp WITHOUT TIME ZONE
            USING "revisado_en" AT TIME ZONE 'America/Santiago',
            ALTER COLUMN "enviado_en" TYPE timestamp WITHOUT TIME ZONE
            USING "enviado_en" AT TIME ZONE 'America/Santiago';
    END IF;
END $$;
