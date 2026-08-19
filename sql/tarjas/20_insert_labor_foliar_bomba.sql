-- =============================================================================
-- TARJAS: Insertar variante de texto faltante para labor FOLIAR
-- Issue #124: "APLIC  MANUAL FOLIAR ( bomba espalada)" (tal como la escribe
-- AppSheet, con doble espacio y paréntesis) no existía en tarjas_labores,
-- causando que las líneas de HERBI ML SPA / TALAGANTE (17 y 18 de agosto de
-- 2026) aparecieran como ⚠ Incompleta y quedaran excluidas del export a Odoo.
--
-- El catálogo ya tenía "APLIC MANUAL FOLIAR-BOMBA ESPALDA" (código 4.2) para
-- la misma labor con puntuación distinta. Se agrega la variante exacta como
-- alias del mismo código, siguiendo el mismo patrón usado para
-- "APLIC MANUAL HERBICIDA", que ya tiene dos filas (con y sin paréntesis)
-- apuntando a codigo_labor = 5.1.
--
-- No hay producto equivalente en Odoo BigQuery (odoo_data.Producto) con
-- "FOLIAR" en el nombre, por lo que _sync_labores no puede resolver esta
-- variante automáticamente — requiere INSERT manual, igual que el issue #32.
-- =============================================================================
INSERT INTO appsheet.tarjas_labores (codigo_labor, labor)
VALUES
    ('4.2', 'APLIC  MANUAL FOLIAR ( bomba espalada)')
ON CONFLICT DO NOTHING;
