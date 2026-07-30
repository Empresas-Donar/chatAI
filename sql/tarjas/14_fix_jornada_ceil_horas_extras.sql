-- =============================================================================
-- TARJAS: Corregir total_jornada calculado con horas_extras redondeadas hacia arriba
-- Issue #62
--
-- 12 filas "Al día" (campo ZUÑIGA, contratistas HERBI ML SPA y
-- MULTISERVICIOS BONHOMIA SPA, 23-29 julio 2026) tienen total_jornada
-- calculado con horas_extras redondeado hacia arriba (CEIL) en vez del valor
-- decimal real — el campo horas_extras y total_hora_extra ya están correctos,
-- solo total_jornada no los usa directamente.
--
-- Confirmado con un caso real reportado: Rodolfo Henríquez Ahumada, 29 julio
-- (id_Resumen=310c0ca1) — 7 horas + 1.5h extra a $3.000/hora + $3.400/hora
-- extra = $21.000 + $5.100 = $26.100, pero el sistema calculó $27.800
-- (usando 2h extra → $6.800 en vez de $5.100).
--
-- Corrección: total_jornada = valor_jornada * horas_trabajadas + total_hora_extra
-- (usando el total_hora_extra ya correcto, sin recalcular horas_extras).
-- Cascada: total_trabajado, contratista_jornada (markup 50%, verificado para
-- ambos contratistas), total_contratista, total_pagar.
--
-- Verificado antes de aplicar: total_trato y contratista_trato son 0 en las
-- 12 filas (pagos "Al día" puros, sin componente de trato).
-- =============================================================================

BEGIN;

WITH bug_rows AS (
    SELECT "id_Resumen",
           (valor_jornada * horas_trabajadas + total_hora_extra) AS new_total_jornada
    FROM appsheet.tarjas_pagos
    WHERE lower(tipo_pago) IN ('al dia', 'al día')
      AND horas_extras > 0
      AND ABS(total_jornada - (valor_jornada * horas_trabajadas + CEIL(horas_extras) * 3400)) < 1
      AND horas_extras != CEIL(horas_extras)
)
UPDATE appsheet.tarjas_pagos p
SET total_jornada = bug_rows.new_total_jornada,
    total_trabajado = bug_rows.new_total_jornada + COALESCE(p.total_trato, 0),
    contratista_jornada = ROUND(bug_rows.new_total_jornada * 0.5),
    total_contratista = ROUND(bug_rows.new_total_jornada * 0.5) + COALESCE(p.contratista_trato, 0),
    total_pagar = (bug_rows.new_total_jornada + COALESCE(p.total_trato, 0))
                  + (ROUND(bug_rows.new_total_jornada * 0.5) + COALESCE(p.contratista_trato, 0))
FROM bug_rows
WHERE bug_rows."id_Resumen" = p."id_Resumen";

COMMIT;
