"""Cosecha detalle operacional: predio filter, floor, and scan totals.

The piece rate and the daily floor stay on the capacho. They do not use
tarjas_empresa factors.
"""

import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.cosecha_rendimiento import (  # noqa: E402
    amount_due,
    filter_options,
    fold,
    predios_for_empresa,
    query_detalle,
)


def test_predios_for_empresa():
    assert predios_for_empresa(None) == ["zuniga", "isla", "talagante"]
    assert predios_for_empresa("") == ["zuniga", "isla", "talagante"]
    assert predios_for_empresa("ZUÑIGA") == ["zuniga"]
    assert predios_for_empresa("Zúñiga") == ["zuniga"]
    assert predios_for_empresa("ISLA DE MAIPO") == ["isla"]
    assert predios_for_empresa("Isla de Maipo") == ["isla"]
    assert predios_for_empresa("TALAGANTE") == ["talagante"]
    assert predios_for_empresa("KONTROLAG") == []


def test_amount_due_adds_the_daily_floor_to_the_piece_rate():
    assert amount_due(10000, 10000) == 20000
    assert amount_due(4000, 10000) == 14000
    assert amount_due(12000, 10000) == 22000
    assert amount_due(None, None) == 0


def _connect():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=20,
    )


@pytest.fixture
def cur():
    conn = _connect()
    conn.set_session(readonly=True, autocommit=True)
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
        conn.close()


def test_zuniga_day_squares_trato_and_floor(cur):
    data = query_detalle(cur, "2026-10-20", "2026-10-20", empresa="ZUÑIGA")
    rows = data["rows"]
    assert rows, "expected Zúñiga scans on 2026-10-20"
    assert data["totales"]["capachos"] == sum(r["capachos"] for r in rows)
    assert data["totales"]["trato"] == sum(r["trato"] for r in rows)
    assert data["totales"]["a_pagar"] == sum(r["a_pagar"] for r in rows)
    assert data["totales"]["capachos"] == sum(r["capachos"] for r in data["resumen"])
    for row in rows:
        assert row["a_pagar"] == row["trato"] + row["piso"]
        assert row["predio"] == "Zúñiga"
        if row["precio"] is not None:
            assert row["trato"] == row["capachos"] * row["precio"]


def test_tarjas_contractor_name_matches_harvest_short_name(cur):
    plain = query_detalle(cur, "2026-10-20", "2026-10-20", empresa="ZUÑIGA")
    named = query_detalle(
        cur,
        "2026-10-20",
        "2026-10-20",
        empresa="ZUÑIGA",
        contratista="SERVICIOS AGRICOLAS PLP SPA",
    )
    other = query_detalle(
        cur,
        "2026-10-20",
        "2026-10-20",
        empresa="ZUÑIGA",
        contratista="AGROSERVICIOS C Y G SPA",
    )
    assert named["totales"]["capachos"] == plain["totales"]["capachos"]
    assert other["totales"]["capachos"] == 0


def test_isla_before_the_app_has_no_rows(cur):
    data = query_detalle(cur, "2025-11-01", "2025-11-30", empresa="ISLA DE MAIPO")
    assert data["rows"] == []
    assert data["totales"]["capachos"] == 0


def test_isla_app_day_adds_the_floor(cur):
    data = query_detalle(cur, "2026-11-10", "2026-11-10", empresa="ISLA DE MAIPO")
    rows = data["rows"]
    assert rows, "expected Isla de Maipo scans on 2026-11-10"
    assert {row["predio"] for row in rows} == {"Isla de Maipo"}
    assert data["totales"]["capachos"] == sum(row["capachos"] for row in rows)
    assert data["totales"]["a_pagar"] == sum(row["a_pagar"] for row in rows)
    for row in rows:
        assert row["a_pagar"] == row["trato"] + row["piso"]
    zuniga = query_detalle(cur, "2026-11-10", "2026-11-10", empresa="ZUÑIGA")
    assert zuniga["totales"]["capachos"] > 0
    assert {row["predio"] for row in zuniga["rows"]} == {"Zúñiga"}
    assert zuniga["totales"]["capachos"] != data["totales"]["capachos"]


def test_open_range_reads_zuniga_and_the_app(cur):
    data = query_detalle(cur, "2025-01-01", "2026-12-31")
    assert data["totales"]["capachos"] > 0
    assert {r["predio"] for r in data["rows"]} == {"Zúñiga", "Isla de Maipo"}


def test_filter_options_follow_each_harvest_app(cur):
    options = filter_options(cur, "TALAGANTE")
    assert "ZUÑIGA" in options["empresas"]
    assert "ISLA DE MAIPO" in options["empresas"]
    assert options["contratistas"] == []

    zuniga = filter_options(cur, "ZUÑIGA")
    assert "PLP" in zuniga["contratistas"]
    assert "Herbi" not in zuniga["contratistas"]
    assert "Gilberto Muñoz" not in zuniga["contratistas"]

    isla = filter_options(cur, "ISLA DE MAIPO")
    assert "Herbi" in isla["contratistas"]
    assert "PLP" not in isla["contratistas"]
    assert "Gilberto Muñoz" not in isla["contratistas"]


def test_empresa_options_follow_the_harvest_in_the_selected_dates(cur):
    assert filter_options(cur, fecha_inicio="2026-10-20", fecha_termino="2026-10-20")["empresas"] == ["ZUÑIGA"]
    assert filter_options(cur, fecha_inicio="2026-11-10", fecha_termino="2026-11-10")["empresas"] == [
        "ZUÑIGA",
        "ISLA DE MAIPO",
    ]
    assert filter_options(cur, fecha_inicio="2025-11-01", fecha_termino="2025-11-30")["empresas"] == []
    assert filter_options(cur, fecha_inicio="2026-10-07", fecha_termino="2026-10-13")["empresas"] == []
    assert filter_options(
        cur,
        contratista="SERVICIOS AGRICOLAS PLP SPA",
        fecha_inicio="2025-01-01",
        fecha_termino="2026-12-31",
    )["empresas"] == ["ZUÑIGA"]


def test_a_second_crew_does_not_add_a_second_floor(cur):
    data = query_detalle(
        cur,
        "2026-11-08",
        "2026-11-08",
        empresa="ZUÑIGA",
        contratista="AGROSERVICIOS M Y G SPA",
    )
    row = next(r for r in data["rows"] if fold(r["trabajador"]) == "GUADALUPE POLO")
    assert row["capachos"] == 14
    assert row["piso"] == 20000
    assert row["a_pagar"] == row["trato"] + 20000
    assert "12" in str(row["cuadrilla"]) and "16" in str(row["cuadrilla"])


def test_empresa_without_harvest_app_is_empty(cur):
    data = query_detalle(cur, "2026-10-01", "2026-10-31", empresa="TALAGANTE")
    assert data["rows"] == []
    assert data["totales"]["capachos"] == 0
