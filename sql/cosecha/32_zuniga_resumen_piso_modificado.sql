-- =============================================================================
-- Cosecha Zúñiga: el resumen por bin usa el piso modificado
--
-- Si hay fila en cosecha_zuniga_salidas_trabajador para ese bin y ese
-- trabajador, accion_piso reemplaza al piso del escaneo en esa fila.
-- Los otros bins no cambian. comentario trae el motivo y va vacío
-- cuando el piso no se modificó.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE OR REPLACE VIEW cosecha_zuniga_resumen_bin_trabajador AS
WITH base AS (
  SELECT
    e.id_registro,
    e.id_qr,
    e.id_bins,
    COALESCE(e.fecha, e.fecha_y_hora::date) AS fecha,
    e.fecha_y_hora,
    COALESCE(e.precio_trato_aplicado::numeric, t.precio_capacho::numeric) AS precio,
    COALESCE(e.piso_aplicado::numeric, t.piso_garantizado_diario::numeric) AS piso_escaneo
  FROM cosecha_zuniga_escaneo e
  LEFT JOIN cosecha_zuniga_tratos t ON t.id_trato = e.id_trato
  WHERE e.id_registro IS NOT NULL
    AND e.id_qr IS NOT NULL
),
agg AS (
  SELECT
    id_registro,
    id_qr,
    max(id_bins) AS id_bins,
    count(*) AS capachos,
    max(precio) AS valor_trato,
    max(piso_escaneo) AS piso_escaneo,
    max(fecha_y_hora) AS ultimo,
    (array_agg(fecha ORDER BY fecha_y_hora DESC NULLS LAST))[1] AS fecha
  FROM base
  GROUP BY id_registro, id_qr
),
marcado AS (
  SELECT
    a.*,
    s.accion_piso,
    s.comentario,
    row_number() OVER (
      PARTITION BY a.fecha, a.id_qr
      ORDER BY a.ultimo DESC NULLS LAST, a.id_registro DESC
    ) AS n
  FROM agg a
  LEFT JOIN cosecha_zuniga_salidas_trabajador s
    ON s.fecha = a.fecha
   AND s.id_qr = a.id_qr
)
SELECT
  id_registro || '-' || id_qr AS id_resumen,
  id_registro,
  id_qr,
  capachos,
  valor_trato,
  COALESCE(accion_piso, piso_escaneo) AS piso,
  capachos * valor_trato AS total_capachos,
  capachos * valor_trato
    + CASE
        WHEN accion_piso IS NULL THEN COALESCE(piso_escaneo, 0)
        WHEN n = 1 THEN accion_piso
        ELSE 0
      END AS total_a_recibir,
  CASE
    WHEN accion_piso IS NULL THEN NULL
    ELSE comentario
  END AS comentario
FROM marcado;

COMMENT ON VIEW cosecha_zuniga_resumen_bin_trabajador IS
  'Capachos, trato y piso por bin. Si hay salida ese día, el piso de todos los bins es accion_piso y el monto entra una vez, en el bin del último capacho.';

COMMENT ON COLUMN cosecha_zuniga_resumen_bin_trabajador.comentario IS
  'Motivo guardado al modificar el piso. Vacío si el piso es el del escaneo.';

COMMIT;
