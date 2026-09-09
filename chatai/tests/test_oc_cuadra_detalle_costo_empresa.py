"""
Orden de compra must square with Detalle operacional Costo Empresa.

AppSheet pagar_efectivo (trabajado + comisión) applied ~45% on Trato and
~50% on Al Día — the inverse of the platform factors. /odoo/tarjas therefore
showed TOTAL A TRATO $2.925.200 vs Detalle $3.027.000 for the reported week.

Orden de facturación and the Odoo CSV export are unchanged.

Reported URL:
  /odoo/tarjas?inp-date-from=2026-09-02&inp-date-to=2026-09-08
  &inp-contratista=MULTISERVICIOS BONHOMIA SPA&inp-empresa=ZUÑIGA

Run:
    python -m pytest chatai/tests/test_oc_cuadra_detalle_costo_empresa.py -v
"""

import inspect
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.purchase_orders_controller as poc  # noqa: E402
import controllers.tarjas_controller as tc  # noqa: E402
import tarjas_empresa as te  # noqa: E402

CONTRATISTA = "MULTISERVICIOS BONHOMIA SPA"
EMPRESA = "ZUÑIGA"
FECHA_INICIO = "2026-09-02"
FECHA_TERMINO = "2026-09-08"


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


class TestOcSquaresDetalleCostoEmpresa:
    def test_oc_header_matches_detalle_resumen(self, conn):
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
        by_tipo = {r["tipo_pago"]: r for r in resumen}
        assert "trato" in by_tipo
        detalle_al_dia = sum(
            float(r["total_empresa"] or 0)
            for r in resumen
            if r.get("tipo_pago") != "trato"
        )

        oc = run(
            poc.get_purchase_order(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        header = oc["header"]
        assert header is not None
        assert header["total_trato"] == pytest.approx(
            by_tipo["trato"]["total_empresa"], abs=1.0
        )
        assert header["total_al_dia"] == pytest.approx(detalle_al_dia, abs=1.0)
        assert header["total"] == pytest.approx(
            sum(float(r["total_empresa"] or 0) for r in resumen), abs=1.0
        )
        assert header["total_trato"] == pytest.approx(3_027_000, abs=1.0)
        assert header["total_al_dia"] == pytest.approx(4_845_658, abs=1.0)

    def test_facturacion_header_matches_detalle_resumen(self, conn):
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
        detalle_trato = next(
            float(r["total_empresa"]) for r in resumen if r["tipo_pago"] == "trato"
        )
        detalle_al_dia = sum(
            float(r["total_empresa"] or 0)
            for r in resumen
            if r.get("tipo_pago") != "trato"
        )
        detalle_trab = sum(float(r["total_trabajado"] or 0) for r in resumen)

        fact = run(
            poc.billing_order_data(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        header = fact["header"]
        assert header is not None
        assert header["total_trato"] == pytest.approx(detalle_trato, abs=1.0)
        assert header["total_al_dia"] == pytest.approx(detalle_al_dia, abs=1.0)
        assert header["total_trabajado"] == pytest.approx(detalle_trab, abs=0.01)
        assert header["total"] == pytest.approx(
            header["total_trabajado"] + header["total_contratista"], abs=0.01
        )
        assert header["total_trato"] == pytest.approx(3_027_000, abs=1.0)
        assert header["total_al_dia"] == pytest.approx(4_845_658, abs=1.0)
        assert header["pct_comision_trato"] == pytest.approx(50.0, abs=0.1)
        assert header["pct_comision_al_dia"] == pytest.approx(45.0, abs=0.1)

    def test_oc_uses_pagos_not_reporte_billable(self):
        src = inspect.getsource(poc._purchase_order_lines)
        assert "FROM appsheet.tarjas_pagos" in src
        assert "SUM(total_trabajado)" in src
        assert "FROM appsheet.tarjas_reporte" not in src
        assert "total_empresa" in src
        pdf_src = inspect.getsource(poc.purchase_order_print_pdf)
        assert "_purchase_order_lines" in pdf_src
        fact_src = inspect.getsource(poc.billing_order_pdf)
        assert "_purchase_order_lines" not in fact_src

    def test_oc_does_not_use_swapped_appsheet_markup(self, conn):
        """Trato must be ×1.50, not AppSheet's ~×1.45 on trabajado."""
        oc = run(
            poc.get_purchase_order(
                contratista=CONTRATISTA,
                empresa=EMPRESA,
                fecha_inicio=FECHA_INICIO,
                fecha_termino=FECHA_TERMINO,
            )
        )
        trato_trab = sum(
            float(r["total_trabajado"] or 0)
            for r in oc["rows"]
            if r.get("tipo_pago") == "trato"
        )
        assert trato_trab > 0
        appsheet_trato = float(te.total_empresa("Al dia", trato_trab))
        platform_trato = float(te.total_empresa("trato", trato_trab))
        assert oc["header"]["total_trato"] == pytest.approx(platform_trato, abs=1.0)
        assert oc["header"]["total_trato"] != pytest.approx(appsheet_trato, abs=500)
