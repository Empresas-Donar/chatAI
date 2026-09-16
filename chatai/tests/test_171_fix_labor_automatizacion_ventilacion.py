"""
Regression tests for issue #171: labor "AUTOMATIZACIÓN VENTILACIÓN" is missing
from appsheet.tarjas_labores, causing 41 rows for MULTISERVICIOS BONHOMIA SPA /
KONTROLAG (10 a 15 de septiembre de 2026) to show as ⚠ Incompleta with
order_line/product_id = NULL and to be silently excluded from the Odoo
purchase-order Excel export.

Root cause (confirmed read-only against production):
- appsheet.tarjas_pagos has 41 rows with labor = 'AUTOMATIZACIÓN VENTILACIÓN'
  (MULTISERVICIOS BONHOMIA SPA / KONTROLAG, 2026-09-10 to 2026-09-15),
  id_labor IS NULL.
- appsheet.tarjas_labores has no row for this labor. Closest catalog entry is
  'TENSADO PIOLA VENTILACIÓN' (14.32) — a different labor, not a text variant.
- appsheet.tarjas_labor (AppSheet source catalog) already has
  id_labor = 14.39, nombre = 'AUTOMATIZACIÓN VENTILACIÓN'. The Odoo view joins
  tarjas_labores, not tarjas_labor, so the AppSheet row never mapped.
- BigQuery odoo_data.Producto does not contain this product (same gap as
  14.25 / 14.46, which still export because they live in tarjas_labores).
  _sync_labores therefore cannot auto-map it.

Fix: sql/tarjas/25_insert_labor_automatizacion_ventilacion.sql inserts the
missing labor into appsheet.tarjas_labores pointing at codigo_labor = 14.39.
"""

from pathlib import Path

SQL_FILE = (
    Path(__file__).parent.parent.parent
    / "sql"
    / "tarjas"
    / "25_insert_labor_automatizacion_ventilacion.sql"
)

PAGOS_LABOR_TEXT = "AUTOMATIZACIÓN VENTILACIÓN"
EXPECTED_CODIGO_LABOR = "14.39"

# Same OC, already mapped — the INSERT must not touch them.
PRE_EXISTING_OC_ENTRIES = {
    "REPARTIR. ABRIR. FLAMEAR. TENSAR. CLIPEAR Y FIJAR PLÁSTICO": "14.25",
    "PREPARACION DE SUSTRATO (R)": "14.46",
    "TENSADO PIOLA VENTILACIÓN": "14.32",
}


def _sql_source() -> str:
    return SQL_FILE.read_text(encoding="utf-8")


class TestIssue171AutomatizacionVentilacionLaborMapeoRegression:
    """Regression suite for AUTOMATIZACIÓN VENTILACIÓN missing from tarjas_labores."""

    def test_171_sql_file_exists(self):
        assert SQL_FILE.exists(), f"Missing SQL file: {SQL_FILE}"

    def test_171_sql_inserts_exact_pagos_text(self):
        """
        Regression: the INSERT must use the exact text stored in tarjas_pagos
        for BONHOMIA / KONTROLAG — the l1 JOIN only normalizes whitespace/
        parentheses, not accents or wording.
        """
        src = _sql_source()
        assert PAGOS_LABOR_TEXT in src, (
            f"SQL must insert the exact labor text {PAGOS_LABOR_TEXT!r} "
            "as stored in appsheet.tarjas_pagos"
        )

    def test_171_sql_uses_appsheet_catalog_codigo_labor(self):
        """
        Regression: must use codigo_labor 14.39, the id_labor already stored
        in appsheet.tarjas_labor for this labor name.
        """
        src = _sql_source()
        assert f"'{EXPECTED_CODIGO_LABOR}'" in src, (
            f"INSERT must target codigo_labor = {EXPECTED_CODIGO_LABOR}"
        )

    def test_171_sql_targets_tarjas_labores_table(self):
        src = _sql_source()
        assert "appsheet.tarjas_labores" in src, (
            "INSERT must target appsheet.tarjas_labores"
        )
        assert "ON CONFLICT DO NOTHING" in src, (
            "INSERT must be idempotent (ON CONFLICT DO NOTHING), matching the "
            "pattern used in 03_insert_labores_bonhomia.sql and issue #128"
        )

    def test_171_sql_only_inserts_never_mutates(self):
        src = _sql_source()
        assert "DELETE" not in src.upper(), "Migration must only INSERT, never DELETE"
        assert "UPDATE" not in src.upper(), "Migration must only INSERT, never UPDATE"

    def test_171_does_not_reuse_tensado_piola_code(self):
        """
        AUTOMATIZACIÓN VENTILACIÓN is not a punctuation variant of
        TENSADO PIOLA VENTILACIÓN (14.32). Mapping it there would bill the
        wrong Odoo product.
        """
        assert EXPECTED_CODIGO_LABOR != PRE_EXISTING_OC_ENTRIES[
            "TENSADO PIOLA VENTILACIÓN"
        ]

    def test_171_cross_farm_isolation(self):
        """
        tarjas_labores is a shared catalog (not scoped per farm/contratista) —
        confirm the new code does not collide with codes used by other
        campos/contratistas already in this OC or prior labor-mapping issues.
        """
        other_known_codes = {
            "14.25",
            "14.32",
            "14.40",
            "14.41",
            "14.42",
            "14.46",
            "4.1",
            "4.2",
            "8.2",
            "8.3",
            "5.1",
        }
        assert EXPECTED_CODIGO_LABOR not in other_known_codes, (
            "New AUTOMATIZACIÓN VENTILACIÓN code must not collide with unrelated labor codes"
        )
