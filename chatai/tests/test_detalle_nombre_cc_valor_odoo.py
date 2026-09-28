"""
Detalle 'Nombre CC' uses tarjas_cc.cultivo when it is a real name, and
'{code} (N cuarteles)' when cultivo is the code and valor_odoo splits
across several analytic CCs (distribution models).

Run:
    python -m pytest chatai/tests/test_detalle_nombre_cc_valor_odoo.py -v
"""

import ast
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc  # noqa: E402

TARJAS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "tarjas_controller.py"
)


def _fn_source(name: str) -> str:
    src = TARJAS_CTRL.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"function {name} not found")


def test_query_selects_valor_odoo_not_only_cultivo():
    src = _fn_source("_query_detalle_rows")
    assert "cc.valor_odoo" in src
    assert "_apply_nombre_cc" in src


def test_nombre_cc_keeps_real_cultivo_name():
    assert (
        tc._nombre_cc_label("883", "CEREZOS SANTINA 2014", {"407": 100})
        == "CEREZOS SANTINA 2014"
    )


def test_nombre_cc_distribution_model_counts_cuarteles():
    valor = {
        "404": 25.53,
        "406": 6.8,
        "407": 6.42,
        "408": 0.71,
        "409": 5.13,
        "410": 1.8,
        "411": 7.19,
        "412": 0.09,
        "413": 7.06,
        "416": 4.75,
        "417": 1.86,
        "418": 2.89,
        "568": 0.13,
        "726": 7.32,
        "727": 7.32,
        "728": 7.12,
        "729": 7.88,
    }
    assert tc._nombre_cc_label("800", "800", valor) == "800 (17 cuarteles)"


def test_nombre_cc_skips_empty_valor_odoo_key():
    assert (
        tc._nombre_cc_label("866", "866", {"": 100, "416": 50, "417": 50})
        == "866 (2 cuarteles)"
    )


def test_nombre_cc_json_string_valor_odoo():
    assert (
        tc._nombre_cc_label("880", "880", '{"406": 51.45, "407": 48.55}')
        == "880 (2 cuarteles)"
    )


def test_nombre_cc_single_key_without_name_keeps_code():
    assert tc._nombre_cc_label("800", "800", {"404": 100}) == "800"


def test_nombre_cc_missing_catalog_is_none():
    assert tc._nombre_cc_label("999", None, None) is None


def test_cc_filter_label_pairs_code_and_name():
    assert tc._cc_filter_label("800", "CAMPO ZÚÑIGA", None) == "800 — CAMPO ZÚÑIGA"
    assert tc._cc_filter_label("800", "800", {"404": 50, "406": 50}) == "800"


def test_query_hora_ponderada_joins_cultivo():
    src = _fn_source("_query_hora_ponderada_rows")
    assert "cc.cultivo" in src
    assert "_apply_nombre_cc" in src
    valor = {
        "404": 25.53,
        "406": 6.8,
        "407": 6.42,
        "408": 0.71,
        "409": 5.13,
        "410": 1.8,
        "411": 7.19,
        "412": 0.09,
        "413": 7.06,
        "416": 4.75,
        "417": 1.86,
        "418": 2.89,
        "568": 0.13,
        "726": 7.32,
        "727": 7.32,
        "728": 7.12,
        "729": 7.88,
    }
    assert tc._nombre_cc_label("800", "CAMPO ZÚÑIGA", valor) == "CAMPO ZÚÑIGA"


def test_live_catalog_800_and_883():
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_cc::text, cultivo, valor_odoo
                FROM appsheet.tarjas_cc
                WHERE id_cc IN ('800', '883')
                """
            )
            rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    finally:
        conn.close()
    assert "800" in rows
    assert tc._nombre_cc_label("800", *rows["800"]) == "CAMPO ZÚÑIGA"
    assert "883" in rows
    assert tc._nombre_cc_label("883", *rows["883"]) == rows["883"][0]
