"""Harvest pay stays off the tarjas company factor and matches the scans."""

import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from db import get_connection  # noqa: E402
from controllers.purchase_orders_controller import cosecha_odoo_lines  # noqa: E402
from tarjas_empresa import total_empresa  # noqa: E402
from services.cosecha_pago import calendar_counts, payable  # noqa: E402
from services.cosecha_rendimiento import amount_due, fold, query_detalle  # noqa: E402


def test_calendar_counts_capachos_and_distinct_bins():
    """A day shows scanned capachos and distinct bins. The bin number is not summed."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            zuniga = calendar_counts(
                cur, "2026-11-10", "2026-11-10", "2026-11-10", "2026-11-10", None, "ZUÑIGA"
            )
            isla = calendar_counts(
                cur,
                "2026-11-10",
                "2026-11-10",
                "2026-11-10",
                "2026-11-10",
                None,
                "ISLA DE MAIPO",
            )
            week = calendar_counts(
                cur, "2026-11-04", "2026-11-10", "2026-11-04", "2026-11-10", None, None
            )
    finally:
        conn.close()
    assert zuniga["days"]["2026-11-10"] == {"capachos": 2742, "bins": 80}
    assert isla["days"]["2026-11-10"] == {"capachos": 224, "bins": 11}
    assert week["capachos"] == 26333
    assert week["capachos"] == sum(day["capachos"] for day in week["days"].values())
    assert 0 < week["bins"] < week["capachos"]
    assert week["bins"] <= sum(day["bins"] for day in week["days"].values())


def test_talagante_has_no_harvest_pay():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            data = payable(cur, "2026-10-20", "2026-10-27", None, "TALAGANTE")
        assert data["total"] == 0
        assert data["lines"] == []
    finally:
        conn.close()


def test_tarjas_legal_name_pays_the_isla_app_and_exports():
    from controllers.purchase_orders_controller import (
        cosecha_odoo_lines,
        group_odoo_export_rows,
    )

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            short = payable(cur, "2026-11-07", "2026-11-10", "Herbi", "ISLA DE MAIPO")
            legal = payable(cur, "2026-11-07", "2026-11-10", "HERBI ML SPA", "ISLA DE MAIPO")
            lines = cosecha_odoo_lines(
                cur, "HERBI ML SPA", "ISLA DE MAIPO", "2026-11-07", "2026-11-10"
            )
            exported, excluded = group_odoo_export_rows(lines)
    finally:
        conn.close()
    assert short["total"] == legal["total"] > 0
    assert sum(line["total_trabajado"] for line in lines) == legal["total"]
    assert sum(line["total"] for line in lines) == float(
        total_empresa("trato", legal["pago_trato"])
    ) + float(total_empresa("al dia", legal["pago_al_dia"]))
    assert excluded == 0
    assert exported
    assert "402" in exported[0][3]


def test_isla_app_pay_adds_the_floor_and_stays_off_zuniga():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            isla = payable(cur, "2026-11-10", "2026-11-10", None, "ISLA DE MAIPO")
            zuniga = payable(cur, "2026-11-10", "2026-11-10", None, "ZUÑIGA")
            detalle = query_detalle(cur, "2026-11-10", "2026-11-10", empresa="ISLA DE MAIPO")
    finally:
        conn.close()
    assert isla["capachos"] > 0
    assert isla["total"] == detalle["totales"]["a_pagar"]
    assert isla["total"] == isla["trato"] + isla["piso"]
    assert isla["capachos"] != zuniga["capachos"]
    assert all(line["cc"] for line in isla["lines"])


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
            assert lines[0]["total_trabajado"] == 193_000
            assert sum(line["total"] for line in lines) == float(total_empresa("trato", 193_000))
            assert {line["product_id"] for line in lines} == {"12.2"}
            assert len(lines) == 1
            assert lines[0]["cc"] == "894"
            assert lines[0]["qty"] == 1
            assert lines[0]["price_unit"] == float(total_empresa("trato", 193_000))
            assert '"410": 100.00' in lines[0]["analytic"]
            assert lines[0]["labor"] == "COSECHA"
            daily = cosecha_odoo_lines(
                cur,
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
                "2026-10-26",
                "2026-10-27",
            )
            worker = sum(item["total_trabajado"] for item in daily)
            assert worker > 0
            assert sum(item["total"] for item in daily) == float(total_empresa("trato", worker))
            assert {item["cc"] for item in daily} == {"894", "895"}
            assert {item["labor"] for item in daily} == {"COSECHA"}
            by_cc = {item["cc"]: item for item in daily}
            assert '"410": 100.00' in by_cc["894"]["analytic"]
            assert '"411": 100.00' in by_cc["895"]["analytic"]
    finally:
        conn.close()


def test_cosecha_odoo_line_adds_the_contractor_rate():
    from controllers.purchase_orders_controller import _apply_cosecha_adicional

    lines = [
        {"qty": 1, "al_dia": False, "total_trabajado": 173_599},
        {"qty": 1, "al_dia": False, "total_trabajado": 354_401},
    ]
    _apply_cosecha_adicional(lines)
    assert sum(line["total_trabajado"] for line in lines) == 528_000
    assert sum(line["total"] for line in lines) == float(total_empresa("trato", 528_000))
    assert sum(line["adicional"] for line in lines) == float(total_empresa("trato", 528_000)) - 528_000
    geraldina = [{"qty": 1, "al_dia": False, "total_trabajado": 1_005_500}]
    _apply_cosecha_adicional(geraldina)
    assert geraldina[0]["total"] == 1_457_975
    assert geraldina[0]["adicional"] == 452_475
    assert geraldina[0]["price_unit"] == 1_457_975


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


# Cuadrilla 8 of Gutiérrez II stopped at 10:13 on 2026-10-29.
# Alex Guevara is on the same roster but scanned in cuadrilla 1.
_ABANDONO_29 = {
    "JUANA MUNOZ": 3,
    "DIANA MEDINA": 3,
    "MARGARITA MUNOZ": 4,
    "PAUL CHEBERRIA": 4,
    "JAVIER DURAN": 4,
    "ADOLFO GARCIA": 4,
    "JOSE SANCHEZ": 5,
    "ELISABET ARCE": 5,
    "DADDY MENDEZ": 6,
    "VICTORIA TAPIA": 6,
    "RAUL MONTANO": 6,
    "YOHN MERIDA": 8,
}


def test_abandono_drops_the_floor_and_keeps_the_capachos():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            gutierrez = payable(
                cur,
                "2026-10-29",
                "2026-10-29",
                "SERVICIOS AGRICOLAS GUTIERREZ II SPA",
                "ZUÑIGA",
            )
            left = {
                fold(row["trabajador"]): row
                for row in gutierrez["personas_dias"]
                if fold(row["trabajador"]) in _ABANDONO_29
            }
            assert set(left) == set(_ABANDONO_29)
            for name, row in left.items():
                assert row["capachos"] == _ABANDONO_29[name]
                assert row["piso"] == 0
                assert row["trato"] == row["capachos"] * 800
                assert row["a_pagar"] == row["trato"]
            stayed = [
                row
                for row in gutierrez["personas_dias"]
                if fold(row["trabajador"]) not in _ABANDONO_29
            ]
            assert stayed
            assert all(row["piso"] > 0 for row in stayed)
            assert sum(row["capachos"] for row in left.values()) == 58
            assert sum(row["trato"] for row in left.values()) == 58 * 800
            cur.execute(
                """
                SELECT DISTINCT trabajador, rut, codigo_qr
                FROM appsheet.cosecha_zuniga_salidas_trabajador
                WHERE fecha = DATE '2026-10-29'
                  AND accion_piso = 0
                """
            )
            fichas = cur.fetchall()
            assert len(fichas) == 13
            assert all(nombre and rut and qr for nombre, rut, qr in fichas)
            assert any(qr == "cos;AAAL7405" for _, _, qr in fichas)
            cur.execute(
                """
                SELECT count(*), count(DISTINCT id_qr)
                FROM appsheet.cosecha_zuniga_salidas_trabajador
                WHERE fecha = DATE '2026-10-29'
                  AND accion_piso = 0
                """
            )
            rows, people = cur.fetchone()
            assert rows == 13
            assert people == 13

            plp = payable(
                cur,
                "2026-10-29",
                "2026-10-29",
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
            )
            alex = next(
                row for row in plp["personas_dias"] if fold(row["trabajador"]) == "ALEX GUEVARA"
            )
            assert alex["capachos"] == 6
            assert alex["piso"] == 0
            assert alex["a_pagar"] == 6 * 800
            others = [
                row for row in plp["personas_dias"] if fold(row["trabajador"]) != "ALEX GUEVARA"
            ]
            assert others
            assert all(row["piso"] > 0 for row in others)

            detail = query_detalle(
                cur,
                "2026-10-29",
                "2026-10-29",
                empresa="ZUÑIGA",
                cuadrilla=8,
            )
    finally:
        conn.close()

    crew = [row for row in detail["rows"] if fold(row["trabajador"]) in _ABANDONO_29]
    assert sum(row["capachos"] for row in crew) == 58
    assert sum(row["piso"] for row in crew) == 0
    assert sum(row["a_pagar"] for row in crew) == 58 * 800


def test_salida_covers_every_bin_of_the_day():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM appsheet.cosecha_zuniga_salidas_trabajador
                WHERE id_qr = '2a7f38a3'
                  AND fecha = DATE '2026-10-29'
                  AND accion_piso = 0
                """
            )
            assert cur.fetchone()[0] == 1
            cur.execute(
                """
                SELECT DISTINCT id_bins
                FROM appsheet.cosecha_zuniga_escaneo
                WHERE id_qr = '2a7f38a3'
                  AND COALESCE(fecha, fecha_y_hora::date) = DATE '2026-10-29'
                """
            )
            bins = [row[0] for row in cur.fetchall()]
            assert len(bins) >= 2
            data = payable(cur, "2026-10-29", "2026-10-29", None, "ZUÑIGA")
            juana = next(
                row
                for row in data["personas_dias"]
                if fold(row["trabajador"]) == "JUANA MUNOZ"
            )
            assert juana["piso"] == 0
            assert juana["a_pagar"] == juana["trato"]
            cur.execute(
                """
                SELECT r.id_bins, v.piso
                FROM appsheet.cosecha_zuniga_resumen_bin_trabajador v
                JOIN appsheet.cosecha_zuniga_registro r
                  ON r.id_registro = v.id_registro
                WHERE v.id_qr = '2a7f38a3'
                  AND r.id_bins = ANY(%s)
                """,
                (bins,),
            )
            shown = {row[0]: int(row[1]) for row in cur.fetchall()}
            assert set(shown) == set(bins)
            assert all(piso == 0 for piso in shown.values())
    finally:
        conn.close()


# Cuadrilla 7 of Gutiérrez II arrived late on Thursday 2026-10-29.
# The floor that remains is 10000, not the 15000 copied on the scan.
_TARDE_29 = {
    "ABIGAIL HERNANDEZ": 11,
    "DAMIAN DONOSO": 8,
    "JONATHAN LEIVA": 10,
    "RANDY ANEZ": 10,
    "LIMBER ROSADO": 6,
    "MARINA COTRINA": 16,
    "GROVER REYES": 5,
}


def test_late_arrival_replaces_the_floor_with_10000():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            gutierrez = payable(
                cur,
                "2026-10-29",
                "2026-10-29",
                "SERVICIOS AGRICOLAS GUTIERREZ II SPA",
                "ZUÑIGA",
            )
            late = {
                fold(row["trabajador"]): row
                for row in gutierrez["personas_dias"]
                if fold(row["trabajador"]) in _TARDE_29
            }
            assert set(late) == set(_TARDE_29)
            for name, row in late.items():
                assert row["capachos"] == _TARDE_29[name]
                assert row["piso"] == 10_000
                assert row["trato"] == row["capachos"] * 800
                assert row["a_pagar"] == row["trato"] + 10_000
            on_time = [
                row
                for row in gutierrez["personas_dias"]
                if fold(row["trabajador"]) in {"EDDY HERBAS", "FERNANDO LARA"}
            ]
            assert len(on_time) == 2
            assert all(row["piso"] == 15_000 for row in on_time)
    finally:
        conn.close()


def _assert_surfaces_square(cur, inicio, termino, contratista):
    data = payable(cur, inicio, termino, contratista, "ZUÑIGA")
    detail = query_detalle(
        cur, inicio, termino, empresa="ZUÑIGA", contratista=contratista
    )
    odoo = cosecha_odoo_lines(cur, contratista, "ZUÑIGA", inicio, termino)
    assert data["total"] == sum(row["a_pagar"] for row in data["personas_dias"])
    assert data["total"] == sum(line["total_labor"] for line in data["lines"])
    assert data["total"] == sum(item["total"] for item in data["cuarteles_pago"])
    assert data["total"] == sum(line["total_trabajado"] for line in odoo)
    assert sum(line["total"] for line in odoo) == float(
        total_empresa("trato", data["pago_trato"])
    ) + float(total_empresa("al dia", data["pago_al_dia"]))
    assert detail["totales"]["a_pagar"] == data["total"]
    assert detail["totales"]["capachos"] == data["capachos"]
    by_person: dict[tuple, int] = {}
    for row in detail["rows"]:
        key = (str(row["fecha"]), fold(row["trabajador"]))
        by_person[key] = by_person.get(key, 0) + row["piso"]
    pay: dict[tuple, int] = {}
    for row in data["personas_dias"]:
        key = (str(row["fecha"]), fold(row["trabajador"]))
        pay[key] = pay.get(key, 0) + row["piso"]
    assert by_person == pay


def test_modified_floor_squares_detail_purchase_order_and_billing():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _assert_surfaces_square(
                cur,
                "2026-10-29",
                "2026-10-29",
                "SERVICIOS AGRICOLAS GUTIERREZ II SPA",
            )
            _assert_surfaces_square(
                cur,
                "2026-10-28",
                "2026-10-31",
                "SERVICIOS AGRICOLAS GUTIERREZ II SPA",
            )
            _assert_surfaces_square(cur, "2026-10-29", "2026-10-29", None)
    finally:
        conn.close()
