-- TARJAS: Trigger para poblar id_labor automáticamente en cada INSERT/UPDATE
-- Issue #27: tarjas_pagos.id_labor debe usar codigo_labor de tarjas_labores

CREATE OR REPLACE FUNCTION appsheet.set_id_labor()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.labor IS NOT NULL AND trim(NEW.labor) != '' THEN
        SELECT codigo_labor INTO NEW.id_labor
        FROM appsheet.tarjas_labores
        WHERE trim(labor) = trim(NEW.labor)
        ORDER BY id
        LIMIT 1;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_set_id_labor ON appsheet.tarjas_pagos;

CREATE TRIGGER trg_set_id_labor
BEFORE INSERT OR UPDATE OF labor ON appsheet.tarjas_pagos
FOR EACH ROW EXECUTE FUNCTION appsheet.set_id_labor();
