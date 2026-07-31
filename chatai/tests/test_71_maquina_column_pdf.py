"""
Regression tests for issue #71: the tractorista detail PDF
(GET /api/tarjas/tractorista/download-pdf) did not show which machine
(appsheet.tarjas_pagos.maquina) was used for each row. Added a "Máquina"
column to the right of "Labor", and removed the per-date "Subtotal"
rows (only the grand TOTAL row remains) per explicit user request while
this was being built.

Rows without a machine (e.g. "OPERARIO SOLO", maquina IS NULL) must show
a placeholder ("–") rather than break the table layout.
"""

import asyncio
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc  # noqa: E402

TARJAS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "tarjas_controller.py"
)


def _pdf_function_source() -> str:
    src = TARJAS_CTRL.read_text(encoding="utf-8")
    start = src.index("async def download_tarjas_tractorista_pdf")
    end = src.index("\n@router", start)
    return src[start:end]


def run(coro):
    return asyncio.run(coro)


async def _bytes(resp):
    if getattr(resp, "body", None):
        return resp.body
    return b"".join([c async for c in resp.body_iterator])


CONTRATISTA = "RAMÓN DIAZ"
CAMPO = "TALAGANTE"
FECHA_INICIO = "2026-07-01"
FECHA_TERMINO = "2026-07-31"


def test_71_maquina_column_present_in_source_regression():
    fn = _pdf_function_source()
    assert ">Máquina<" in fn, "the flat table must have a Máquina header"
    assert 'r["maquina"]' in fn, "row cells must read maquina from the query"


def test_71_no_subtotal_rows_in_source_regression():
    """Per-date 'Subtotal' rows were removed on explicit user request —
    only the grand TOTAL row should remain."""
    fn = _pdf_function_source()
    assert "Subtotal" not in fn, "per-date subtotal rows must be gone"
    assert ">TOTAL<" in fn, "the grand total row must still be there"


def test_71_query_selects_maquina_regression():
    fn = _pdf_function_source()
    assert "maquina" in fn
    assert "GROUP BY fecha::date, trabajador, labor, maquina" in fn


def test_71_pdf_still_renders_with_maquina_column():
    resp = run(
        tc.download_tarjas_tractorista_pdf(
            contratista=CONTRATISTA,
            campo=CAMPO,
            fecha_inicio=FECHA_INICIO,
            fecha_termino=FECHA_TERMINO,
            cc=None,
        )
    )
    body = run(_bytes(resp))
    assert body[:4] == b"%PDF"


def test_71_rows_without_machine_do_not_crash_query():
    """OPERARIO SOLO rows have maquina IS NULL — must not raise and must
    still be included (not silently dropped) in the underlying query."""
    conn = tc.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT fecha::date::text AS fecha, trabajador, labor, maquina,
                       SUM(total_tractor) AS monto
                FROM appsheet.tarjas_pagos
                WHERE LOWER(TRIM(tipo_pago)) = 'tractorista'
                  AND contratista = %s AND nombre_campo = %s
                  AND fecha::date BETWEEN %s AND %s
                GROUP BY fecha::date, trabajador, labor, maquina
                ORDER BY fecha::date, trabajador, labor
                """,
                (CONTRATISTA, CAMPO, FECHA_INICIO, FECHA_TERMINO),
            )
            rows = tc._rows_to_dicts(cur)
    finally:
        conn.close()
    assert any(r["maquina"] is None for r in rows), (
        "expected at least one OPERARIO SOLO row with maquina IS NULL in this dataset"
    )
    assert any(r["maquina"] is not None for r in rows), (
        "expected at least one row with a real machine in this dataset"
    )
