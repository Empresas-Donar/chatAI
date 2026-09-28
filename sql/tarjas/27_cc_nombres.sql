-- =============================================================================
-- TARJAS: Catálogo de respaldo de nombres de CC
--
-- AppSheet y Odoo muestran códigos (800, 878) para los modelos de distribución
-- analítica. Los Excel de "Códigos de Distribución Analítica" traen el nombre
-- humano (CAMPO ZÚÑIGA, CEREZOS 2014). Esta tabla es el respaldo de esos
-- nombres; sync_cc.py la upserta desde sql/tarjas/cc_nombres.csv y rellena
-- tarjas_cc.cultivo cuando está vacío o es igual al código.
--
-- tipo = 'modelo'  → código de distribución (reparte a varios cuarteles)
-- tipo = 'cuartel' → cuenta analítica hoja (un CC de Odoo)
-- =============================================================================

CREATE TABLE IF NOT EXISTS appsheet.tarjas_cc_nombres (
    "id_cc"      TEXT NOT NULL PRIMARY KEY,
    "nombre"     TEXT NOT NULL,
    "tipo"       TEXT NOT NULL,
    "campo"      TEXT,
    "fuente"     TEXT NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT now()
);
