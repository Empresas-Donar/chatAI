-- =============================================================================
-- Cosecha Zúñiga, viernes 30/10/2026: el piso del día queda en 20.000
--
-- Trabajaron hasta las 17:00. Una fila por persona y fecha: el monto cubre
-- todos los bins y se paga una vez. Los capachos no cambian.
-- El bin anotado es el del último capacho, donde cerró la jornada.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

INSERT INTO cosecha_zuniga_salidas_trabajador (
  id_salida, fecha, id_qr, trabajador, rut, codigo_qr,
  accion_piso, comentario, hora_salida, id_bins, id_trato
)
SELECT
  'salida-20261030-' || e.id_qr,
  DATE '2026-10-30',
  e.id_qr,
  min(e.trabajador),
  min(e.rut_trabajador),
  min(e.codigo_qr),
  20000,
  'trabajaron hasta las 17:00, piso 20000',
  max(e.fecha_y_hora),
  (array_agg(e.id_bins ORDER BY e.fecha_y_hora DESC))[1],
  (array_agg(COALESCE(b.id_trato, e.id_trato) ORDER BY e.fecha_y_hora DESC))[1]
FROM cosecha_zuniga_escaneo e
LEFT JOIN cosecha_zuniga_bins b ON b.id_bins = e.id_bins
WHERE COALESCE(e.fecha, e.fecha_y_hora::date) = DATE '2026-10-30'
  AND e.id_qr IS NOT NULL
GROUP BY e.id_qr
ON CONFLICT ON CONSTRAINT cosecha_zuniga_salidas_fecha_qr DO UPDATE
  SET trabajador = EXCLUDED.trabajador,
      rut = EXCLUDED.rut,
      codigo_qr = EXCLUDED.codigo_qr,
      accion_piso = EXCLUDED.accion_piso,
      comentario = EXCLUDED.comentario,
      hora_salida = EXCLUDED.hora_salida,
      id_bins = EXCLUDED.id_bins,
      id_trato = EXCLUDED.id_trato;

COMMIT;
