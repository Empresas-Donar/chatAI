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


def test_bulk_reportes_include_the_same_harvest_as_the_web():
    """The /reportes PDF builders are the web PDF. Harvest is added, not factored."""
    import controllers.tarjas_controller as tc
    from tarjas_empresa import annotate_detalle_resumen

    fi, ft = "2026-10-26", "2026-10-27"
    contratista = "SERVICIOS AGRICOLAS PLP SPA"
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            pay = payable(cur, fi, ft, contratista, "ZUÑIGA")
            where, params = tc._build_detalle_filters(
                fi, ft, contratista, "ZUÑIGA", None, None, None, None
            )
            tarjas_only = annotate_detalle_resumen(
                tc._query_detalle_resumen(cur, where, params)
            )
            detalle = tc._build_detalle_html(
                cur, fi, ft, contratista=contratista, empresa="ZUÑIGA"
            )
            general = tc._build_general_html(
                cur, fi, ft, contratista=contratista, empresa="ZUÑIGA"
            )
            persona = tc._build_contratista_html(
                cur, fi, ft, contratista=contratista, empresa="ZUÑIGA"
            )
            resumen = tc._build_resumen_persona_html(
                cur, fi, ft, contratista=contratista, empresa="ZUÑIGA"
            )
            isla = tc._build_general_html(
                cur, fi, ft, contratista=contratista, empresa="ISLA DE MAIPO"
            )
    finally:
        conn.close()

    assert pay["total"] == 528_000
    assert pay["pago_al_dia"] == 528_000
    wrong_rows = []
    for row in tarjas_only:
        copy = {
            "tipo_pago": row["tipo_pago"],
            "total_trabajado": float(row["total_trabajado"] or 0),
            "jornadas": row["jornadas"],
        }
        if tc._fold_tipo(copy["tipo_pago"]) == "al dia":
            copy["total_trabajado"] += pay["total"]
        wrong_rows.append(copy)
    if not any(tc._fold_tipo(row["tipo_pago"]) == "al dia" for row in wrong_rows):
        wrong_rows.append(
            {"tipo_pago": "Al dia", "total_trabajado": pay["total"], "jornadas": 24}
        )
    wrong = sum(row["total_empresa"] for row in annotate_detalle_resumen(wrong_rows))
    right = sum(float(row["total_empresa"]) for row in tarjas_only) + pay["total"]
    assert tc._fmt_clp(right) in detalle
    assert wrong != right
    assert tc._fmt_clp(wrong) not in detalle
    assert "COSECHA" in detalle
    assert "Cosecha · Al día" in general
    assert tc._fmt_clp(pay["total"]) in general
    assert "COSECHA · al día" in persona
    assert tc._fmt_clp(22_000) in resumen
    assert "Cosecha · Al día" not in isla

    import asyncio
    import io

    import openpyxl

    async def sheet(coro):
        resp = await coro
        body = b""
        async for chunk in resp.body_iterator:
            body += chunk
        return openpyxl.load_workbook(io.BytesIO(body)).active

    detalle_xl = asyncio.run(
        sheet(tc.download_tarjas_detalle_excel(fi, ft, contratista, "ZUÑIGA", None, None, None, None))
    )
    general_xl = asyncio.run(
        sheet(tc.download_tarjas_general_excel(fi, ft, None, None, None, contratista, "ZUÑIGA"))
    )
    persona_xl = asyncio.run(
        sheet(tc.download_tarjas_contratista_excel(fi, ft, contratista, "ZUÑIGA", None, None, None))
    )
    assert int(detalle_xl.cell(detalle_xl.max_row, 9).value) == int(right)
    cosecha_general = sum(
        row[7] or 0
        for row in general_xl.iter_rows(min_row=2, values_only=True)
        if row[2] in ("Cosecha", "Cosecha · Al día")
    )
    assert cosecha_general == pay["total"]
    cosecha_persona = [
        row
        for row in persona_xl.iter_rows(min_row=2, values_only=True)
        if row[2] in ("COSECHA", "COSECHA · al día")
    ]
    assert cosecha_persona
    assert sum(row[-1] or 0 for row in cosecha_persona) == pay["total"]
