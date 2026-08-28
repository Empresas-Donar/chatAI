-- =============================================================================
-- TARJAS: Corregir total_jornada con hora extra omitida por completo
-- Issue #82 — misma causa raíz que #62, variante "omisión" en vez de CEIL
--
-- Descubierto por el barrido completo de verificación de #82 (test de
-- regresión) DESPUÉS de corregir a Cristian González y crear el trigger
-- permanente (20_fix_jornada_ceil_cristian_gonzalez.sql,
-- 21_trigger_fix_total_jornada.sql) — estas 2 filas se sincronizaron desde
-- AppSheet en el mismo rango de fechas y quedaron con total_jornada=0 pese
-- a tener total_hora_extra=1700 (hora extra completamente omitida del
-- cálculo, no solo redondeada). Mismo patrón ya visto una vez en #62 para
-- id_Resumen='c874eed9'.
--
-- Maibet Lobo, contratista HERBI ML SPA, campo ZUÑIGA, labor PODA:
--   id_Resumen = 'cb9a21d3' (4 agosto 2026), '034056fd' (3 agosto 2026)
--
-- contratista_jornada (850) y total_contratista (850) ya estaban correctos
-- (850 = 50% de 1700, el total_jornada correcto) — no se tocan.
--
-- El trigger de 21_trigger_fix_total_jornada.sql ya cubre este patrón hacia
-- adelante (recalcula total_jornada en cualquier INSERT/UPDATE con
-- discrepancia >$500, sin importar si la causa es CEIL u omisión total).
-- Este script solo corrige las 2 filas que ya existían antes de crear el
-- trigger.
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_pagos p
SET total_jornada    = (valor_jornada * horas_trabajadas + total_hora_extra),
    total_trabajado  = (valor_jornada * horas_trabajadas + total_hora_extra) + COALESCE(p.total_trato, 0),
    total_pagar      = ((valor_jornada * horas_trabajadas + total_hora_extra) + COALESCE(p.total_trato, 0))
                        + COALESCE(p.total_contratista, 0)
WHERE p."id_Resumen" IN ('cb9a21d3', '034056fd');

COMMIT;
