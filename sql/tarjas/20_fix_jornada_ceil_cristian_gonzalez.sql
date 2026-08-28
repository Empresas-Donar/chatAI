-- =============================================================================
-- TARJAS: Corregir total_jornada calculado con horas_extras redondeadas
-- hacia arriba (CEIL) — recurrencia de issue #62
-- Issue #82
--
-- 2 filas idénticas (misma tarja, dos id_tarja_supervisor distintos) de
-- Cristian González Dinamarca, contratista MULTISERVICIOS BONHOMIA SPA,
-- campo ZUÑIGA, 3 de agosto de 2026, labor APLIC FOLIAR TURBO:
--   id_Resumen = 'eb9f5d80', '7e0da2e5'
--
-- horas_extras=5.5, total_hora_extra=18700 (correcto: 5.5*3400) pero
-- total_jornada=20400 = CEIL(5.5)*3400 = 6*3400. Mismo bug de #62: la fila
-- usa horas_extras redondeado hacia arriba en vez del valor decimal real.
--
-- contratista_jornada (9350) y total_contratista (9350) YA estaban
-- correctos (9350 = 50% de 18700, el total_jornada correcto) — AppSheet los
-- calcula de forma independiente al campo total_jornada roto, así que no se
-- tocan.
--
-- Verificado antes de aplicar: barrido completo de las 727 filas "Al día"
-- de appsheet.tarjas_pagos — estas son las únicas 2 con una discrepancia
-- real (>$500) entre total_jornada y valor_jornada*horas_trabajadas +
-- total_hora_extra. El resto es ruido de redondeo de $1-3 ya documentado y
-- aceptado en #62 (no se toca).
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_pagos p
SET total_jornada   = (valor_jornada * horas_trabajadas + total_hora_extra),
    total_trabajado = (valor_jornada * horas_trabajadas + total_hora_extra) + COALESCE(p.total_trato, 0),
    total_pagar      = ((valor_jornada * horas_trabajadas + total_hora_extra) + COALESCE(p.total_trato, 0))
                        + COALESCE(p.total_contratista, 0)
WHERE p."id_Resumen" IN ('eb9f5d80', '7e0da2e5');

COMMIT;
