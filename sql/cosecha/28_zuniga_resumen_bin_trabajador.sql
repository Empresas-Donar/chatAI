-- =============================================================================
-- Cosecha Zúñiga: resumen de pago por bin y trabajador
--
-- Una fila por apertura de bin (id_registro) y trabajador (id_qr).
-- total_a_recibir = capachos × trato + piso.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE OR REPLACE VIEW cosecha_zuniga_resumen_bin_trabajador AS
SELECT
  e.id_registro || '-' || e.id_qr                      AS id_resumen,
  e.id_registro,
  e.id_qr,
  COUNT(*)                                             AS capachos,
  MAX(COALESCE(e.precio_trato_aplicado::numeric, t.precio_capacho::numeric))          AS valor_trato,
  MAX(COALESCE(e.piso_aplicado::numeric, t.piso_garantizado_diario::numeric))         AS piso,
  COUNT(*) * MAX(COALESCE(e.precio_trato_aplicado::numeric, t.precio_capacho::numeric)) AS total_capachos,
  COUNT(*) * MAX(COALESCE(e.precio_trato_aplicado::numeric, t.precio_capacho::numeric))
  + COALESCE(MAX(COALESCE(e.piso_aplicado::numeric, t.piso_garantizado_diario::numeric)), 0)
                                                       AS total_a_recibir
FROM cosecha_zuniga_escaneo e
LEFT JOIN cosecha_zuniga_tratos t ON t.id_trato = e.id_trato
WHERE e.id_registro IS NOT NULL
  AND e.id_qr IS NOT NULL
GROUP BY e.id_registro, e.id_qr;

COMMENT ON VIEW cosecha_zuniga_resumen_bin_trabajador IS
  'Capachos, trato y piso por apertura de bin y trabajador. total_a_recibir = capachos x trato + piso.';

COMMIT;
