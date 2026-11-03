-- =============================================================================
-- Cosecha Zúñiga: salida de un trabajador y decisión del piso
--
-- El piso se paga una vez por persona y día. Esta fila existe solo cuando
-- alguien reemplaza ese piso. accion_piso es el monto que queda: 0 no paga
-- piso y los capachos se conservan. Sin fila, se paga el piso del escaneo.
--
-- id_qr es el del escaneo. Varios de estos trabajadores no están en
-- cosecha_zuniga_qr, así que no hay REFERENCES a ese catálogo.
-- El grano es el bin y el trabajador. La fecha es la del escaneo.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE TABLE IF NOT EXISTS cosecha_zuniga_salidas_trabajador (
  id_salida      text PRIMARY KEY,
  fecha          date NOT NULL,
  id_qr          text NOT NULL,
  trabajador     text,
  rut            text,
  codigo_qr      text,
  accion_piso    numeric NOT NULL,
  comentario     text,
  hora_salida    timestamp NOT NULL,
  registrado_por text,
  id_bins        text REFERENCES cosecha_zuniga_bins (id_bins),
  id_trato       text REFERENCES cosecha_zuniga_tratos (id_trato),
  created_at     timestamp NOT NULL DEFAULT now(),
  CONSTRAINT cosecha_zuniga_salidas_bins_qr UNIQUE (id_bins, id_qr)
);

ALTER TABLE cosecha_zuniga_salidas_trabajador
  ADD COLUMN IF NOT EXISTS trabajador text,
  ADD COLUMN IF NOT EXISTS rut text,
  ADD COLUMN IF NOT EXISTS codigo_qr text;

-- La primera versión guardaba QUITAR_PISO / DEJAR_PISO. Ahora es el monto.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'appsheet'
      AND table_name = 'cosecha_zuniga_salidas_trabajador'
      AND column_name = 'accion_piso'
      AND udt_name IN ('text', 'varchar')
  ) THEN
    ALTER TABLE cosecha_zuniga_salidas_trabajador
      DROP CONSTRAINT IF EXISTS cosecha_zuniga_salidas_trabajador_accion_piso_check;
    ALTER TABLE cosecha_zuniga_salidas_trabajador
      ALTER COLUMN accion_piso TYPE numeric
      USING CASE
        WHEN btrim(accion_piso) IN ('QUITAR_PISO', '0') THEN 0
        ELSE NULLIF(btrim(accion_piso), '')::numeric
      END;
  END IF;
END $$;

ALTER TABLE cosecha_zuniga_salidas_trabajador
  DROP CONSTRAINT IF EXISTS cosecha_zuniga_salidas_trabajador_accion_piso_check;

ALTER TABLE cosecha_zuniga_salidas_trabajador
  ADD CONSTRAINT cosecha_zuniga_salidas_trabajador_accion_piso_check
  CHECK (accion_piso >= 0);

CREATE INDEX IF NOT EXISTS idx_salidas_bins
  ON cosecha_zuniga_salidas_trabajador (id_bins);

COMMENT ON TABLE cosecha_zuniga_salidas_trabajador IS
  'Reemplazo del piso de un trabajador en un bin. accion_piso es el monto que queda. Sin fila, ese bin paga el piso del escaneo.';

COMMENT ON COLUMN cosecha_zuniga_salidas_trabajador.accion_piso IS
  'Piso que reemplaza al del trato, en CLP. 0 no paga piso.';

COMMENT ON COLUMN cosecha_zuniga_salidas_trabajador.hora_salida IS
  'Hora del hecho. created_at es cuándo se registró.';

COMMENT ON COLUMN cosecha_zuniga_salidas_trabajador.trabajador IS
  'Nombre con el que escaneó ese día.';

COMMENT ON COLUMN cosecha_zuniga_salidas_trabajador.rut IS
  'RUT con el que escaneó ese día.';

COMMENT ON COLUMN cosecha_zuniga_salidas_trabajador.codigo_qr IS
  'Código QR que usó ese día, el de escaneo.codigo_qr.';

-- 29/10/2026. La cuadrilla 8 de Gutiérrez II paró a las 10:13.
-- Alex Guevara no estaba en esa cuadrilla: escaneó en la 1 y paró a las 09:40.
INSERT INTO cosecha_zuniga_salidas_trabajador (
  id_salida, fecha, id_qr, trabajador, rut, codigo_qr,
  accion_piso, comentario, hora_salida, id_bins, id_trato
)
SELECT
  'salida-20261029-' || e.id_qr,
  DATE '2026-10-29',
  e.id_qr,
  min(e.trabajador),
  min(e.rut_trabajador),
  min(e.codigo_qr),
  0,
  CASE
    WHEN e.id_qr = '427b49ac'
      THEN 'abandono; escaneó en la cuadrilla 1, no en la 8'
    ELSE 'abandono cuadrilla 8'
  END,
  max(e.fecha_y_hora),
  (array_agg(e.id_bins ORDER BY e.fecha_y_hora DESC))[1],
  (array_agg(e.id_trato ORDER BY e.fecha_y_hora DESC))[1]
FROM cosecha_zuniga_escaneo e
WHERE COALESCE(e.fecha, e.fecha_y_hora::date) = DATE '2026-10-29'
  AND e.id_qr IN (
    '2a7f38a3', -- Juana Muñoz
    'e78123e6', -- Diana Medina
    '546dc1f4', -- Margarita muñoz
    '6cb0acee', -- Paul cheberria
    'a20f233d', -- Javier duran
    '1b10c108', -- Adolfo García
    'f5347c21', -- José Sánchez
    'b0ece3c9', -- Elisabet arce
    'e97cd8b0', -- Daddy Mendez
    'bcb891f5', -- Victoria tapia
    '800800ac', -- Raul montaño
    'b046960a', -- Yohn Mérida
    '427b49ac'  -- Alex guevara, cuadrilla 1
  )
GROUP BY e.id_qr
ON CONFLICT ON CONSTRAINT cosecha_zuniga_salidas_bins_qr DO UPDATE
  SET trabajador = EXCLUDED.trabajador,
      rut = EXCLUDED.rut,
      codigo_qr = EXCLUDED.codigo_qr,
      accion_piso = EXCLUDED.accion_piso,
      comentario = EXCLUDED.comentario,
      hora_salida = EXCLUDED.hora_salida,
      id_bins = EXCLUDED.id_bins,
      id_trato = EXCLUDED.id_trato;

-- 29/10/2026. La cuadrilla 7 de Gutiérrez II llegó tarde.
-- El piso que queda es 10.000, no el de 15.000 del escaneo.
-- hora_salida es el primer capacho: el hecho es la llegada.
INSERT INTO cosecha_zuniga_salidas_trabajador (
  id_salida, fecha, id_qr, trabajador, rut, codigo_qr,
  accion_piso, comentario, hora_salida, id_bins, id_trato
)
SELECT
  'salida-20261029-' || e.id_qr,
  DATE '2026-10-29',
  e.id_qr,
  min(e.trabajador),
  min(e.rut_trabajador),
  min(e.codigo_qr),
  10000,
  'llegada tarde cuadrilla 7',
  min(e.fecha_y_hora),
  (array_agg(e.id_bins ORDER BY e.fecha_y_hora))[1],
  (array_agg(e.id_trato ORDER BY e.fecha_y_hora))[1]
FROM cosecha_zuniga_escaneo e
WHERE COALESCE(e.fecha, e.fecha_y_hora::date) = DATE '2026-10-29'
  AND e.id_qr IN (
    'b3d3dce2', -- Abigail hernandez
    '529c10e2', -- Damian donoso
    '2b0193b0', -- Jonathan leiva
    '3d837395', -- Randy añez
    'd0270aa3', -- Limber rosado
    '92e6f590', -- Marina cotrina
    '98d7e1d3'  -- Grover reyes
  )
GROUP BY e.id_qr
ON CONFLICT ON CONSTRAINT cosecha_zuniga_salidas_bins_qr DO UPDATE
  SET trabajador = EXCLUDED.trabajador,
      rut = EXCLUDED.rut,
      codigo_qr = EXCLUDED.codigo_qr,
      accion_piso = EXCLUDED.accion_piso,
      comentario = EXCLUDED.comentario,
      hora_salida = EXCLUDED.hora_salida,
      id_bins = EXCLUDED.id_bins,
      id_trato = EXCLUDED.id_trato;

COMMIT;
