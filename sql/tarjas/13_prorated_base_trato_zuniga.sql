-- =============================================================================
-- TARJAS: Recalcular base_trato con prorrateo por horas_trabajadas/horas_trabajar
-- Issue #60 — reemplaza la regla del issue #46 ("solo el primer registro del
-- día recibe la base completa") por una regla proporcional aplicada a cada
-- registro de trato individualmente, sin importar duplicados el mismo día.
--
-- Fórmula: base_trato = ROUND(plan.base * horas_trabajadas / plan.horas_trabajar)
-- donde plan viene de appsheet.tarjas_trato (catálogo de planes de precio por
-- id_campo + id_labor + tipo_pago + rango de fechas vigente).
--
-- Alcance: solo campo ZUÑIGA (decisión explícita del usuario, no todos los
-- campos). 335 filas de trato (88 Pendiente + 247 Aprobado), todas con match
-- sin ambigüedad contra tarjas_trato (base y horas_trabajar consistentes al
-- 100% entre los planes que matchean cada fila, aunque varios matcheen por
-- distintos niveles de "valor").
--
-- El JOIN usa comparación NUMÉRICA de id_labor (no texto) — mismo problema de
-- ceros finales del issue #58 (ej. '7.20' vs '7.2' como texto no son iguales).
--
-- Los 6 campos derivados se recalculan en cascada:
--   total_trato        = base_trato + rendimiento * valor_trato
--   total_trabajado     = total_trato (sin componente de jornada en filas de trato)
--   contratista_trato   = ROUND(total_trato * 0.45)  -- markup verificado en Zuñiga
--   total_contratista    = contratista_trato (sin componente de jornada)
--   total_pagar          = total_trabajado + total_contratista
--
-- Verificado antes de aplicar: 0 filas de Zuñiga con total_jornada o
-- contratista_jornada distinto de 0 (simplifica la cascada arriba).
-- =============================================================================

BEGIN;

WITH plan AS (
    SELECT DISTINCT ON (p."id_Resumen") p."id_Resumen",
           t.base::numeric AS plan_base,
           t.horas_trabajar::numeric AS plan_horas
    FROM appsheet.tarjas_pagos p
    JOIN appsheet.tarjas_campo c ON c.nombre = p.nombre_campo
    JOIN appsheet.tarjas_trato t
      ON t.id_campo = c.id_campo::text
     AND t.id_labor::numeric = p.id_labor::numeric
     AND t.tipo_pago = 'trato'
     AND p.fecha::date BETWEEN t.fecha_inicio::date AND t.fecha_fin::date
    WHERE p.tipo_pago = 'trato' AND p.nombre_campo = 'ZUÑIGA'
    ORDER BY p."id_Resumen", t.id_trato
),
computed AS (
    SELECT plan."id_Resumen",
           ROUND(plan.plan_base * p.horas_trabajadas / plan.plan_horas) AS new_base_trato,
           ROUND(plan.plan_base * p.horas_trabajadas / plan.plan_horas)
               + COALESCE(p.rendimiento, 0) * COALESCE(p.valor_trato, 0) AS new_total_trato
    FROM plan
    JOIN appsheet.tarjas_pagos p ON p."id_Resumen" = plan."id_Resumen"
)
UPDATE appsheet.tarjas_pagos p
SET base_trato = computed.new_base_trato,
    total_trato = computed.new_total_trato,
    total_trabajado = computed.new_total_trato,
    contratista_trato = ROUND(computed.new_total_trato * 0.45),
    total_contratista = ROUND(computed.new_total_trato * 0.45),
    total_pagar = computed.new_total_trato + ROUND(computed.new_total_trato * 0.45)
FROM computed
WHERE computed."id_Resumen" = p."id_Resumen";

COMMIT;
