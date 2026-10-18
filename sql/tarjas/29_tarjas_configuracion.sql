-- Umbral para marcar montos en el reporte Detalle contratista.
--
-- Una sola fila, id_configuracion = 'general':
--   umbral_diario  se marca la celda (día o total de la fila) cuando el
--                  monto es mayor a este valor. 30.000 queda sin marca.
--
-- Idempotente: no duplica la fila ni pisa un valor que ya se haya cambiado.
-- El reporte marca todo monto mayor a este número. 30.000 queda sin marca.

CREATE TABLE IF NOT EXISTS appsheet.tarjas_configuracion (
  "id_configuracion" text    PRIMARY KEY,
  "umbral_diario"    numeric NOT NULL DEFAULT 30000
                     CONSTRAINT tarjas_configuracion_umbral_chk
                     CHECK ("umbral_diario" >= 0)
);

INSERT INTO appsheet.tarjas_configuracion ("id_configuracion", "umbral_diario")
VALUES ('general', 30000)
ON CONFLICT ("id_configuracion") DO NOTHING;
