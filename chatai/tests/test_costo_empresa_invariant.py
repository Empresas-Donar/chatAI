"""
Company-pay tarjas surfaces must share Costo Empresa (tarjas_empresa).

Detalle, Orden de compra, Orden de facturación, Nota de crédito and the
Dashboard tarjas totals must agree for the same Aprobado week. AppSheet
total_pagar / trabajado+comisión is not the billed amount.

Reported week: MULTISERVICIOS BONHOMIA SPA / ZUÑIGA / 2026-09-02..08

Run:
    python -m pytest chatai/tests/test_costo_empresa_invariant.py -v
"""

import ast
import inspect
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.dashboard_controller as dash  # noqa: E402
import controllers.purchase_orders_controller as poc  # noqa: E402
import controllers.tarjas_controller as tc  # noqa: E402
import tarjas_empresa as te  # noqa: E402

CONTRATISTA = "MULTISERVICIOS BONHOMIA SPA"
EMPRESA = "ZUÑIGA"
FECHA_INICIO = "2026-09-02"
FECHA_TERMINO = "2026-09-08"
BACKEND = Path(__file__).resolve().parent.parent / "backend"


def run(coro):
    import asyncio

    return asyncio.run(coro)


@pytest.fixture
def conn():
    import psycopg2

    c = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    yield c
    c.rollback()
    c.close()


def _fn_source(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found in {path}")


class TestCompanyPaySurfacesShareCostoEmpresa:
    def test_detalle_oc_facturacion_notas_same_total(self, conn):
        with conn.cursor() as cur:
            where, params = tc._build_detalle_filters(
                FECHA_INICIO,
                FECHA_TERMINO,
                contratista=CONTRATISTA,
                empresa=EMPRESA,
            )
            resumen = te.annotate_detalle_resumen(
                tc._query_detalle_resumen(cur, where, params)
            )
        detalle = sum(float(r["total_empresa"] or 0) for r in resumen)

        oc = run(
            poc.get_purchase_order(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        fact = run(
            poc.billing_order_data(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        notas = run(
            tc.get_tarjas_notas(
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
                campo=EMPRESA,
                contratista=CONTRATISTA,
            )
        )

        assert oc["header"]["total"] == pytest.approx(detalle, abs=1.0)
        assert fact["header"]["total"] == pytest.approx(detalle, abs=1.0)
        assert notas["total_general"] == pytest.approx(detalle, abs=1.0)
        assert oc["header"]["total_trato"] == pytest.approx(2_926_100, abs=1.0)
        assert fact["header"]["total_trato"] == pytest.approx(2_926_100, abs=1.0)

    def test_company_pay_helpers_do_not_use_appsheet_billable(self):
        poc_path = BACKEND / "controllers" / "purchase_orders_controller.py"
        tarjas_path = BACKEND / "controllers" / "tarjas_controller.py"
        dash_path = BACKEND / "controllers" / "dashboard_controller.py"

        oc_src = _fn_source(poc_path, "_purchase_order_lines")
        assert "FROM appsheet.tarjas_pagos" in oc_src
        assert "SUM(total_trabajado)" in oc_src
        assert "total_empresa" in oc_src
        assert "FROM appsheet.tarjas_reporte" not in oc_src

        fact_src = _fn_source(poc_path, "_fetch_billing_order")
        assert "FROM appsheet.tarjas_pagos" in fact_src
        assert "_billing_costo_parts" in fact_src or "total_empresa" in fact_src
        assert "_BILLABLE_SQL" not in fact_src
        assert "SUM(total_pagar)" not in fact_src

        notas_src = _fn_source(tarjas_path, "_query_notas_lines")
        assert "SUM(total_trabajado)" in notas_src
        assert "total_empresa" in notas_src
        assert "SUM(total_pagar)" not in notas_src

        dash_src = inspect.getsource(dash.get_dashboard_data)
        assert "fold_costo_empresa" in dash_src
        assert "tarjas_reporte" not in dash_src
        assert "total_labor" not in dash_src

        bulk = (
            BACKEND / "controllers" / "reports_controller.py"
        ).read_text(encoding="utf-8")
        assert "_build_detalle_html" in bulk

    def test_odoo_export_uses_costo_empresa_helper(self):
        export_src = inspect.getsource(poc.export_odoo_csv)
        assert "costo_empresa_odoo_lines" in export_src
        preview_src = inspect.getsource(poc.get_export_preview)
        assert "costo_empresa_odoo_lines" in preview_src
        notas_src = inspect.getsource(tc.export_tarjas_notas_odoo)
        assert "costo_empresa_odoo_lines" in notas_src

    def test_odoo_export_lines_sum_to_oc_header(self, conn):
        oc = run(
            poc.get_purchase_order(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        with conn.cursor() as cur:
            lines = poc.costo_empresa_odoo_lines(
                cur, CONTRATISTA, EMPRESA, FECHA_INICIO, FECHA_TERMINO
            )
        assert sum(float(l["total"] or 0) for l in lines) == pytest.approx(
            oc["header"]["total"], abs=1.0
        )

    def test_no_magic_factors_in_company_pay_controllers(self):
        frontend = BACKEND.parent / "frontend" / "static"
        for rel in (
            "controllers/purchase_orders_controller.py",
            "controllers/dashboard_controller.py",
        ):
            src = (BACKEND / rel).read_text(encoding="utf-8")
            assert "1.45" not in src
            assert "1.50" not in src
        for name in (
            "tarjas_detail.js",
            "purchase_orders.js",
            "billing_order.js",
            "despacho_notas.js",
            "dashboard.js",
        ):
            src = (frontend / name).read_text(encoding="utf-8")
            assert "1.45" not in src, name
            assert "1.50" not in src, name

    def test_document_pages_auto_load_from_shared_url(self):
        frontend = BACKEND.parent / "frontend" / "static"
        for name in ("purchase_orders.js", "billing_order.js", "despacho_notas.js"):
            src = (frontend / name).read_text(encoding="utf-8")
            assert "autoTriggerFromURL" in src, name
            assert "no auto-trigger" not in src, name
