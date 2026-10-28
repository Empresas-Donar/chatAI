"""Harvest pay stays off the tarjas company factor and matches the scans."""

import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from db import get_connection  # noqa: E402
from controllers.purchase_orders_controller import cosecha_odoo_lines  # noqa: E402
from services.cosecha_pago import TIPO_AL_DIA, payable  # noqa: E402
from services.cosecha_rendimiento import amount_due  # noqa: E402


def test_talagante_has_no_harvest_pay():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            data = payable(cur, "2026-10-20", "2026-10-27", None, "TALAGANTE")
        assert data["total"] == 0
        assert data["lines"] == []
    finally:
        conn.close()


def test_zuniga_pay_is_piece_rate_plus_one_daily_floor():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            data = payable(cur, "2026-10-20", "2026-10-27", None, "ZUÑIGA")
            assert data["total"] > 0
            assert data["total"] == sum(row["a_pagar"] for row in data["personas_dias"])
            assert data["total"] == sum(line["total_labor"] for line in data["lines"])
            assert data["total"] == sum(item["total"] for item in data["cuarteles_pago"])
            for row in data["personas_dias"]:
                assert row["a_pagar"] == amount_due(row["trato"], row["piso"])
            names = {row["contratista"] for row in data["personas_dias"]}
            assert "SERVICIOS AGRICOLAS PLP SPA" in names
            linked = payable(
                cur,
                "2026-10-20",
                "2026-10-27",
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
            )
            assert 0 < linked["total"] < data["total"]
            assert all(
                row["contratista"] == "SERVICIOS AGRICOLAS PLP SPA"
                for row in linked["personas_dias"]
            )
    finally:
        conn.close()


def test_zero_piece_rate_with_floor_is_daily_pay():
    """Trato dafea3cb sets the capacho price to 0 and the floor to 22000.

    Those person-days are Al día. The amount is the floor once per person
    and day, with no tarjas 50 % markup.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            data = payable(
                cur,
                "2026-10-26",
                "2026-10-27",
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
            )
            daily = [row for row in data["personas_dias"] if row["al_dia"]]
            assert len(daily) == 24
            assert data["pago_al_dia"] == 24 * 22_000
            assert data["pago_trato"] == 0
            for row in daily:
                assert row["trato"] == 0
                assert row["piso"] == 22_000
                assert row["a_pagar"] == 22_000
                assert row["tipo_pago"] == TIPO_AL_DIA
                assert row["tipo_pago"] == "Al dia"
            assert data["total"] == sum(line["total_labor"] for line in data["lines"])
            piece = payable(
                cur,
                "2026-10-20",
                "2026-10-20",
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
            )
            assert piece["pago_al_dia"] == 0
            assert piece["pago_trato"] == piece["total"]
            assert piece["total"] > 0
            assert all(row["tipo_pago"] == "trato" for row in piece["personas_dias"])
    finally:
        conn.close()


def test_harvest_odoo_line_uses_cosecha_manual_and_cuartel_center():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            lines = cosecha_odoo_lines(
                cur,
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
                "2026-10-14",
                "2026-10-20",
            )
            assert sum(line["total"] for line in lines) == 193_000
            assert {line["product_id"] for line in lines} == {"12.2"}
            assert {line["cc"] for line in lines} == {"894"}
            assert all('"410": 100.00' in line["analytic"] for line in lines)
            assert {line["price_unit"] for line in lines} == {1000, 10000}
            daily = cosecha_odoo_lines(
                cur,
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
                "2026-10-26",
                "2026-10-27",
            )
            assert sum(item["total"] for item in daily) == 24 * 22_000
            assert len(daily) == 1
            assert daily[0]["qty"] == 24
            assert daily[0]["price_unit"] == 22_000
            assert '"410": 32.88' in daily[0]["analytic"]
            assert '"411": 67.12' in daily[0]["analytic"]
    finally:
        conn.close()
