-- Marca de revisión del calendario de tarjas.
-- No vive en tarjas_pagos: un sync de AppSheet puede pisar esa tabla
-- y perdería la marca. id_resumen apunta a tarjas_pagos."id_Resumen"
-- sin FK, porque esa tabla no tiene clave primaria declarada.

CREATE TABLE IF NOT EXISTS appsheet.tarjas_pagos_revision (
    id_resumen   TEXT NOT NULL PRIMARY KEY,
    revisado     BOOLEAN NOT NULL DEFAULT TRUE,
    revisado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);
