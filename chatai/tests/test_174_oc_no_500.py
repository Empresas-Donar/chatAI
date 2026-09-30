"""Orden de compra must not 500 while building Nombre CC.

Cloud Run loads the app as chatai.backend.main. A bare
`from tarjas_controller import ...` is ModuleNotFoundError and the
payment screen shows "Error al generar" (HTTP 500), including weeks
that only have tractorista rows and therefore zero cuadrilla lines.

Reported:
  /odoo/tarjas?fil-from=2026-09-23&fil-to=2026-09-29
  &fil-empresa=ZUÑIGA&fil-contratista=AGROSERVICIOS C Y G SPA
"""
import ast
import asyncio
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import controllers.purchase_orders_controller as poc  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent / "backend"
AGRO = "AGROSERVICIOS C Y G SPA"
BONHOMIA = "MULTISERVICIOS BONHOMIA SPA"
EMPRESA = "ZUÑIGA"


def _fn_source(name: str) -> str:
    src = (BACKEND / "controllers" / "purchase_orders_controller.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found")


def test_oc_lines_import_nombre_cc_as_package():
    """Regression: the helper import must resolve under Cloud Run's path."""
    src = _fn_source("_label_nombre_cc")
    assert "from controllers.tarjas_controller import _nombre_cc_label" in src
    lines = _fn_source("_purchase_order_lines")
    assert "from tarjas_controller import" not in lines
    assert "from tarjas_controller import" not in src


def test_missing_cc_name_does_not_drop_the_line():
    """A CC absent from tarjas_cc keeps the code. It must not raise."""
    assert poc._label_nombre_cc("800", None, None) == "800"
    assert poc._label_nombre_cc("800", "800", None) == "800"
    assert poc._label_nombre_cc("800", "CAMPO ZUÑIGA", "{") == "CAMPO ZUÑIGA"
    assert poc._label_nombre_cc(None, None, None) is None


def test_oc_agroservice_week_without_cuadrilla_does_not_500():
    """That week is tractorista-only. The screen must come back empty, not 500."""
    result = asyncio.run(
        poc.get_purchase_order(
            contratista=AGRO,
            empresa=EMPRESA,
            fecha_inicio="2026-09-23",
            fecha_termino="2026-09-29",
        )
    )
    assert result == {"rows": [], "header": None}


def test_oc_bonhomia_week_still_generates():
    """A real cuadrilla week still returns a header. The import fix must not blank it."""
    result = asyncio.run(
        poc.get_purchase_order(
            contratista=BONHOMIA,
            empresa=EMPRESA,
            fecha_inicio="2026-09-02",
            fecha_termino="2026-09-08",
        )
    )
    assert result["header"]["total"] == pytest.approx(7_938_850, abs=1.0)
    assert result["rows"]
    assert all(
        (r.get("tipo_pago") or "").strip().lower() != "tractorista"
        for r in result["rows"]
    )
