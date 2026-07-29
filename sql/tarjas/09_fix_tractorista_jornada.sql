-- =============================================================================
-- TARJAS: Corregir jornada lunes-sábado mal aplicada en tarjas de tractoristas
-- Issue #45
--
-- 65 registros de tractoristas fueron ingresados con la jornada "lunes a
-- sábado" (horas_trabajadas=9.00) en fechas que en realidad corresponden a
-- lunes-viernes, donde debe aplicarse la tarifa lunes-viernes (7.5 horas).
--
-- Reglas (aportadas por el equipo de operaciones, no derivables del esquema):
--   - OPERARIO SOLO / Jornada Tractor simple: tarifa igual en ambos esquemas,
--     solo cambian las horas, el monto no cambia.
--   - Jornada Tractor normal: el monto sí cambia — $72.000 (con licencia /
--     certificado + bono) o $27.600 (sin licencia / certificado, sin bono).
--
-- Verificado antes de aplicar: las 65 filas están en estado Pendiente,
-- tipo_pago='Tractorista', horas_trabajadas=9, y los montos actuales de
-- "Jornada Tractor normal" caen limpiamente en $61.000 o $23.000 (sin
-- valores atípicos), consistente con la regla de arriba.
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = '706df95e';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = '5e2067ac';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '5aec856d';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = 'a0a4cf22';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '6318144c';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = '5f6ec16c';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '4bb18f1e';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = '1494a432';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '1eedb9a5';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '5eef5e55';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = '3c867a4b';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 31000, total_trabajado = 31000, total_pagar = 31000 WHERE "id_Resumen" = '349a01e6';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '0a191749';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = '209478a5';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'e9bddc53';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'de33e6d9';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = 'd73ef626';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '8f35f6dd';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'd322591b';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '0daecd41';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = '86db58e4';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '1c0359e7';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'b578d68a';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = '2a660f68';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '223eda7f';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '574c6591';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = '4807793a';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '84a6fbb3';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'e0714f0f';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = '1b43c652';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'dfe3289b';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '31398f03';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = 'd3740bb9';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'dd13eee4';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'e4498b88';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = '681f0634';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = 'c5a70c3e';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = '67d65fd0';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '598f897e';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = 'd5538dcb';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'c4dcf8d2';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 27600, total_trabajado = 27600, total_pagar = 27600 WHERE "id_Resumen" = 'bef57ba9';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = 'bb862ac2';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = 'ae8d6f70';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 30000, total_trabajado = 30000, total_pagar = 30000 WHERE "id_Resumen" = '7f349bf4';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '047c8146';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'a034ac69';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '7cf31353';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '53503d77';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '5858840a';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '3a4270e3';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'cb30bd0b';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = 'b7bdde75';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '0a9f956d';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = 'a029c9cf';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '6a1d1653';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '6c9c5529';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'a7abc870';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 36000, total_trabajado = 36000, total_pagar = 36000 WHERE "id_Resumen" = '9254073f';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '77d34f63';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'f8c68a5e';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'e3425643';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = '19d178ea';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'cff6a1b6';
UPDATE appsheet.tarjas_pagos SET horas_trabajadas = 7.5, total_tractor = 72000, total_trabajado = 72000, total_pagar = 72000 WHERE "id_Resumen" = 'd3bf8bf9';

COMMIT;
