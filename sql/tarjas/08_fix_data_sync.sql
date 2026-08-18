-- =============================================================================
-- TARJAS: Corregir datos desincronizados en tarjas_pagos
-- Issue #42
--
-- Problema 1: total_contratista quedó desincronizado de sus componentes
-- (contratista_jornada + contratista_trato) en 109 filas — casi siempre en 0
-- mientras los componentes tienen valor real. No afecta tarjas_reporte /
-- tarjas_reporte_odoo (usan total_pagar, ya calculado bien desde los
-- componentes), pero sí es una trampa para el Chat IA y cualquier lectura
-- directa de la columna.
--
-- Problema 2: valor_jornada quedó con un dato incorrecto (2000 en vez de
-- ~3333/hora) en 5 filas de HERBI ML SPA (26-29 mayo 2026). En la fila
-- c32b7713 el error se propagó a total_trabajado y total_pagar, calculados
-- con la tarifa equivocada (18000 en vez de 30000).
--
-- Idempotente: cada UPDATE solo toca filas que aún no coinciden con la
-- fórmula esperada.
-- =============================================================================

BEGIN;

-- ── Problema 1: resincronizar total_contratista ────────────────────────────
UPDATE appsheet.tarjas_pagos
SET total_contratista = COALESCE(contratista_jornada, 0) + COALESCE(contratista_trato, 0)
WHERE ABS(
    COALESCE(total_contratista, 0)
    - (COALESCE(contratista_jornada, 0) + COALESCE(contratista_trato, 0))
) > 1;

-- ── Problema 2: corregir valor_jornada mal ingresado (HERBI ML SPA, mayo 2026) ──
UPDATE appsheet.tarjas_pagos
SET valor_jornada = 3333
WHERE "id_Resumen" IN ('7beaf777', 'c32b7713', '211788c0', 'a8a6a30a', '7eb3e678')
  AND valor_jornada = 2000;

-- ── Problema 2b: recalcular total_trabajado/total_pagar en la fila afectada ──
-- (las otras 4 filas hermanas ya tenían total_trabajado/total_pagar correctos;
--  solo c32b7713 los había calculado con la tarifa equivocada)
UPDATE appsheet.tarjas_pagos
SET total_trabajado = COALESCE(total_jornada, 0) + COALESCE(total_trato, 0),
    total_pagar = COALESCE(total_jornada, 0) + COALESCE(total_trato, 0)
                  + COALESCE(total_contratista, 0)
WHERE "id_Resumen" = 'c32b7713'
  AND total_trabajado != COALESCE(total_jornada, 0) + COALESCE(total_trato, 0);

COMMIT;
