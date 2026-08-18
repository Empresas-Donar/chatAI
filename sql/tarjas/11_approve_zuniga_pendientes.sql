-- =============================================================================
-- TARJAS: Aprobar tarjas Pendientes del campo Zuñiga (23-28 julio 2026)
-- Issue #56
--
-- 311 filas Pendiente, $12.878.657 CLP total, 3 contratistas (Multiservicios
-- Bonhomia SPA, Servicios Agricolas Gutierrez II SPA, Herbi ML SPA).
--
-- Verificado antes de aplicar: total_contratista sincronizado (0 problemas),
-- 0 casos de duplicacion real de base_trato, total_trabajado consistente.
-- 25 filas (~$15.620 CLP, 0.12% del total) con patrones menores ya vistos
-- en el issue #42 (desfase de redondeo de ~$20 en filas con rendimiento
-- fraccionario) y un patron nuevo consistente (+$1.700 en total_jornada,
-- probable cargo/bono real no capturado en el esquema) — aprobadas de
-- todas formas por decision explicita del usuario.
--
-- Idempotente: solo actualiza filas que aun esten en Pendiente.
-- =============================================================================

BEGIN;

UPDATE appsheet.tarjas_pagos
SET estado = 'Aprobado'
WHERE nombre_campo = 'ZUÑIGA'
  AND estado = 'Pendiente';

COMMIT;
