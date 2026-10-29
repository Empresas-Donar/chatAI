-- Traza de procesos autónomos (calidad de cosecha y los que vengan).
-- Cada revisión inserta una fila. No se pisa el historial.
-- La comparación de "datos nuevos" usa la última fila del proceso con enviado = true.

CREATE SCHEMA IF NOT EXISTS intranet;

CREATE TABLE IF NOT EXISTS intranet.proceso_estado (
    id TEXT PRIMARY KEY,
    proceso TEXT NOT NULL,
    huella TEXT,
    enviado BOOLEAN NOT NULL,
    motivo TEXT NOT NULL,
    revisado_en TIMESTAMPTZ NOT NULL,
    enviado_en TIMESTAMPTZ,
    CONSTRAINT intranet_proceso_estado_proceso_chk
        CHECK (btrim(proceso) <> ''),
    CONSTRAINT intranet_proceso_estado_motivo_chk
        CHECK (motivo IN ('sin_datos', 'sin_cambios', 'enviado')),
    CONSTRAINT intranet_proceso_estado_envio_chk
        CHECK (
            (enviado AND motivo = 'enviado' AND enviado_en IS NOT NULL AND huella IS NOT NULL)
            OR (NOT enviado AND motivo = 'sin_datos' AND enviado_en IS NULL AND huella IS NULL)
            OR (NOT enviado AND motivo = 'sin_cambios' AND enviado_en IS NULL AND huella IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS ix_intranet_proceso_estado_proceso_revisado
    ON intranet.proceso_estado (proceso, revisado_en DESC);

CREATE INDEX IF NOT EXISTS ix_intranet_proceso_estado_ultimo_envio
    ON intranet.proceso_estado (proceso, enviado_en DESC)
    WHERE enviado;
