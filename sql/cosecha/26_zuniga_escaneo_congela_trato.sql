-- =============================================================================
-- Cosecha Zúñiga: el escaneo congela precio y piso del trato
--
-- La base ya eligió el trato. AppSheet no escribe estos montos.
-- =============================================================================

BEGIN;

SET LOCAL search_path TO appsheet, pg_catalog;

CREATE OR REPLACE FUNCTION cosecha_registro_bin()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
DECLARE
  v_trato text;
BEGIN
  IF NEW.id_bins IS NULL OR NEW.id_bins = '' THEN
    RAISE EXCEPTION 'El registro no trae id_bins';
  END IF;
  IF NEW.bins IS NULL THEN
    RAISE EXCEPTION 'Falta el código del bin';
  END IF;

  v_trato := cosecha_trato_para(NEW.id_cuartel, NEW.fecha_y_hora::date);
  IF v_trato IS NULL THEN
    RAISE EXCEPTION
      'No hay trato vigente para el cuartel % al %',
      NEW.id_cuartel, NEW.fecha_y_hora::date;
  END IF;

  INSERT INTO cosecha_zuniga_bins (id_bins, bins, id_trato)
  VALUES (NEW.id_bins, NEW.bins, v_trato)
  ON CONFLICT (id_bins) DO UPDATE
    SET bins = EXCLUDED.bins,
        id_trato = EXCLUDED.id_trato;

  IF TG_OP = 'UPDATE' THEN
    UPDATE cosecha_zuniga_escaneo e
    SET id_trato = v_trato,
        bins = NEW.bins::text,
        precio_trato_aplicado = t.precio_capacho,
        piso_aplicado = t.piso_garantizado_diario
    FROM cosecha_zuniga_tratos t
    WHERE e.id_bins = NEW.id_bins
      AND t.id_trato = v_trato
      AND (
        e.id_trato IS DISTINCT FROM v_trato
        OR e.bins IS DISTINCT FROM NEW.bins::text
        OR e.precio_trato_aplicado IS DISTINCT FROM t.precio_capacho
        OR e.piso_aplicado IS DISTINCT FROM t.piso_garantizado_diario
      );
  END IF;

  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION cosecha_escaneo_trato()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = appsheet, pg_catalog
AS $$
BEGIN
  SELECT b.id_trato, b.bins::text, t.precio_capacho, t.piso_garantizado_diario
    INTO NEW.id_trato, NEW.bins, NEW.precio_trato_aplicado, NEW.piso_aplicado
  FROM cosecha_zuniga_bins b
  LEFT JOIN cosecha_zuniga_tratos t ON t.id_trato = b.id_trato
  WHERE b.id_bins = NEW.id_bins;
  RETURN NEW;
END $$;

UPDATE cosecha_zuniga_escaneo e
SET precio_trato_aplicado = t.precio_capacho,
    piso_aplicado = t.piso_garantizado_diario
FROM cosecha_zuniga_tratos t
WHERE t.id_trato = e.id_trato
  AND (
    e.precio_trato_aplicado IS DISTINCT FROM t.precio_capacho
    OR e.piso_aplicado IS DISTINCT FROM t.piso_garantizado_diario
  );

COMMIT;
