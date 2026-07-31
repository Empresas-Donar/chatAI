-- =============================================================================
-- TARJAS: Corregir tarifas de tractoristas (Andrés Díaz mal pagado, filas de
-- sábado y fila incompleta con la columna de tarifa equivocada) y normalizar
-- horas_trabajadas a 9 para todos los ingresos de tractoristas.
-- Issue #64
--
-- Tabla de tarifas real: appsheet.tarjas_labor (no derivable del código, solo
-- de la BD) — columnas valor_c_operador_lunes_viernes / valor_s_operador_*:
--   Jornada Tractor normal: con operador L-V = 66000, sin operador L-V = 27600
--   OPERARIO SOLO:          flat 30000 en las 4 combinaciones (no aplica bono)
--
-- El bono de $6.000 es POR TRABAJADOR (appsheet.tarjas_personal.licencia_clase_d
-- y certificado_sag, ambos 'SI'), no por máquina:
--   ANDRÉS DÍAZ HERRRRA (id_personal 73286f7f): licencia_clase_d='NO', certificado_sag='NO' -> sin bono
--   LUIS IVÁN CONTRERAS PERALTA (a8961a38) y NIVALDO MALDONADO VALENZUELA (f83db9a0):
--     licencia_clase_d='SI', certificado_sag='SI' -> con bono
--
-- Regla de negocio (confirmada por el usuario): todos los ingresos actuales
-- son "con operador"; la tarifa a usar es siempre la de lunes-viernes,
-- independiente del día real de la semana; horas_trabajadas no participa en
-- el cálculo del monto y debe normalizarse a 9 en todos los registros.
--
-- Errores encontrados y corregidos:
--   1) Andrés Díaz "Jornada Tractor normal" (12 filas) estaba usando la
--      columna sin_operador_lunes_viernes ($27.600) en vez de
--      con_operador_lunes_viernes sin bono ($66.000).
--   2) Luis Iván y Nivaldo tenían 1 fila cada uno (sábado 11/07/2026) usando
--      la columna lunes-sábado con bono ($61.000 = 55.000+6.000) en vez de
--      lunes-viernes con bono ($72.000 = 66.000+6.000).
--   3) Fila incompleta de Luis Iván (03/07/2026, horas_trabajadas=1,
--      total=0) — confirmada por el usuario como día trabajado, se corrige
--      igual que sus demás filas de "Jornada Tractor normal".
--
-- Sin cambios (ya correctos, verificados contra la tabla de tarifas):
--   - Andrés Díaz "OPERARIO SOLO" ($30.000, sin bono porque no cumple)
--   - Luis Iván / Nivaldo "OPERARIO SOLO" ($36.000 = 30.000+6.000, con bono)
--   - Luis Iván / Nivaldo "Jornada Tractor normal" entre semana ($72.000)
--   - Nivaldo "Jornada Tractor simple" ($31.000 = 25.000+6.000, con bono)
--
-- Fuera de alcance: no existe rate para "Jornada Tractor simple" comparando
-- entre trabajadores (solo Nivaldo la usa) y ya coincide con el catálogo, no
-- se toca.
-- =============================================================================

BEGIN;

-- 1) Normalizar horas_trabajadas a 9 en TODAS las filas de tractoristas
--    (la tarifa no depende de las horas; deja de usarse el esquema 7.5/9).
UPDATE appsheet.tarjas_pagos
SET horas_trabajadas = 9
WHERE tipo_pago = 'Tractorista';

-- 2) Andrés Díaz Herrrra — "Jornada Tractor normal": con operador, L-V, sin bono = $66.000
--    (12 filas: 11 que estaban en $27.600 + 1 sábado que estaba en $23.000)
UPDATE appsheet.tarjas_pagos
SET total_tractor = 66000, total_trabajado = 66000, total_pagar = 66000
WHERE "id_Resumen" IN (
    'bef57ba9','d5538dcb','67d65fd0','681f0634','d3740bb9','1b43c652',
    '4807793a','2a660f68','de1c7533','86db58e4','d73ef626','209478a5'
);

-- 3) Luis Iván / Nivaldo — "Jornada Tractor normal": con operador, L-V, con bono = $72.000
--    (2 filas de sábado a $61.000 + 1 fila incompleta de Luis Iván a $0)
UPDATE appsheet.tarjas_pagos
SET total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000
WHERE "id_Resumen" IN ('ef32a4e1', '254d8504', '08529b3c');

COMMIT;
