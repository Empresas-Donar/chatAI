"""Harvest pay stays off the tarjas company factor and matches the scans."""

import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from db import get_connection  # noqa: E402
from controllers.purchase_orders_controller import cosecha_odoo_lines  # noqa: E402
from services.cosecha_pago import payable  # noqa: E402
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


def test_floor_only_day_stays_cosecha_trato():
    """Trato dafea3cb sets the capacho price to 0 and the floor to 22000.

    Those person-days are still cosecha a trato. The line is identified as
    piso. The amount is the floor once per person and day, with no tarjas factor.
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
            solo = [row for row in data["personas_dias"] if row["solo_piso"]]
            assert len(solo) == 24
            assert data["pago_trato"] == 24 * 22_000
            assert data["pago_al_dia"] == 0
            assert data["total"] == 24 * 22_000
            for row in solo:
                assert row["trato"] == 0
                assert row["piso"] == 22_000
                assert row["a_pagar"] == 22_000
                assert row["tipo_pago"] == "trato"
                assert row["labor"] == "COSECHA"
                assert row["al_dia"] is False
            floors = [line for line in data["lines"] if line["labor"] == "COSECHA"]
            assert {line["cc"] for line in floors} == {"894", "895"}
            assert sum(line["total_labor"] for line in floors) == 24 * 22_000
            assert all(line["tipo_pago"] == "trato" and not line["al_dia"] for line in floors)
            assert all(row["labor"] == "COSECHA" for row in solo)
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
            gutierrez = payable(
                cur,
                "2026-10-21",
                "2026-10-27",
                "SERVICIOS AGRICOLAS GUTIERREZ II SPA",
                "ZUÑIGA",
            )
            assert gutierrez["total"] == 218_400 + 360_000 + 264_000
            assert gutierrez["pago_al_dia"] == 0
            assert len(gutierrez["lines"]) == 1
            line = gutierrez["lines"][0]
            assert line["labor"] == "COSECHA"
            assert line["tipo_pago"] == "trato"
            assert line["cc"] == "864"
            assert line["total_labor"] == gutierrez["total"]
            assert "SANTINA" in (line["cultivo"] or "").upper()
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
            assert len(lines) == 1
            assert lines[0]["cc"] == "894"
            assert lines[0]["qty"] == 1
            assert lines[0]["price_unit"] == 193_000
            assert '"410": 100.00' in lines[0]["analytic"]
            assert lines[0]["labor"] == "COSECHA"
            daily = cosecha_odoo_lines(
                cur,
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
                "2026-10-26",
                "2026-10-27",
            )
            assert sum(item["total"] for item in daily) == 24 * 22_000
            assert {item["cc"] for item in daily} == {"894", "895"}
            assert {item["labor"] for item in daily} == {"COSECHA"}
            by_cc = {item["cc"]: item for item in daily}
            assert by_cc["894"]["total"] == 173_599
            assert by_cc["895"]["total"] == 354_401
            assert '"410": 100.00' in by_cc["894"]["analytic"]
            assert '"411": 100.00' in by_cc["895"]["analytic"]
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
    assert pay["pago_trato"] == 528_000
    assert pay["pago_al_dia"] == 0
    wrong_rows = []
    for row in tarjas_only:
        copy = {
            "tipo_pago": row["tipo_pago"],
            "total_trabajado": float(row["total_trabajado"] or 0),
            "jornadas": row["jornadas"],
        }
        if tc._fold_tipo(copy["tipo_pago"]) == "trato":
            copy["total_trabajado"] += pay["total"]
        wrong_rows.append(copy)
    if not any(tc._fold_tipo(row["tipo_pago"]) == "trato" for row in wrong_rows):
        wrong_rows.append(
            {"tipo_pago": "trato", "total_trabajado": pay["total"], "jornadas": 24}
        )
    wrong = sum(row["total_empresa"] for row in annotate_detalle_resumen(wrong_rows))
    right = sum(float(row["total_empresa"]) for row in tarjas_only) + pay["total"]
    assert tc._fmt_clp(right) in detalle
    assert wrong != right
    assert tc._fmt_clp(wrong) not in detalle
    assert "COSECHA" in detalle
    assert "894" in detalle and "895" in detalle
    assert "COSECHA ·" not in detalle
    assert "Cosecha" in general
    assert "Cosecha · Al día" not in general
    assert tc._fmt_clp(pay["total"]) in general
    assert "COSECHA" in persona
    assert "COSECHA · piso" not in persona
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
        if row[2] == "COSECHA"
    )
    assert cosecha_general == pay["total"]
    cosecha_persona = [
        row
        for row in persona_xl.iter_rows(min_row=2, values_only=True)
        if row[2] == "COSECHA"
    ]
    assert cosecha_persona
    assert sum(row[-1] or 0 for row in cosecha_persona) == pay["total"]
