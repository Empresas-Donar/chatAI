-- =============================================================================
-- TARJAS: Trigger para autocorregir total_jornada en cada INSERT/UPDATE
-- Issue #82 — salvaguarda permanente para la recurrencia del bug de #62
--
-- AppSheet a veces calcula total_jornada usando horas_extras redondeado
-- hacia arriba (CEIL) en vez del valor decimal real, aunque horas_extras y
-- total_hora_extra en sí llegan correctos (issue #62, recurrencia #82). No
-- hay forma de corregir la fórmula en el origen (AppSheet, fuera de este
-- repo), así que este trigger recalcula total_jornada (y su cascada:
-- total_trabajado, total_pagar) directamente en PostgreSQL cada vez que se
-- inserta o actualiza una fila "Al día" con una discrepancia significativa.
--
-- Umbral de $500: un barrido completo de las 727 filas "Al día" existentes
-- mostró ruido de redondeo inofensivo de $1-3 (valor_jornada almacenado
-- como decimal periódico aproximado) en ~224 filas — no se debe sobrescribir
-- ese ruido histórico ya aceptado. El bug real nunca es menor a $1.700 (una
-- hora extra completa mal contada a $3.400/hora), muy por encima del umbral.
--
-- No toca contratista_jornada/total_contratista: se calculan en AppSheet de
-- forma independiente y no forman parte de este bug (confirmado en #82).
-- =============================================================================

CREATE OR REPLACE FUNCTION appsheet.fix_total_jornada_bug()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_correct NUMERIC;
BEGIN
    IF lower(NEW.tipo_pago) IN ('al dia', 'al día') THEN
        v_correct := COALESCE(NEW.valor_jornada, 0) * COALESCE(NEW.horas_trabajadas, 0)
                     + COALESCE(NEW.total_hora_extra, 0);
        IF ABS(COALESCE(NEW.total_jornada, 0) - v_correct) > 500 THEN
            NEW.total_jornada := v_correct;
            NEW.total_trabajado := v_correct + COALESCE(NEW.total_trato, 0);
            NEW.total_pagar := (v_correct + COALESCE(NEW.total_trato, 0)) + COALESCE(NEW.total_contratista, 0);
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_fix_total_jornada ON appsheet.tarjas_pagos;

CREATE TRIGGER trg_fix_total_jornada
BEFORE INSERT OR UPDATE OF valor_jornada, horas_trabajadas, total_hora_extra, tipo_pago
ON appsheet.tarjas_pagos
FOR EACH ROW EXECUTE FUNCTION appsheet.fix_total_jornada_bug();
