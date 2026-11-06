"""Harvest has no clocked hours. The 9h report still projects it.

Each person-day counts as one 9-hour jornada, split across cost centers in
the same proportion as the pay. The cell is then the day's pay (the average
when several people share the labor and CC).
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from controllers.tarjas_controller import (  # noqa: E402
    _hora_ponderada_9h,
    _load_hora_ponderada_rows,
)
from db import get_connection  # noqa: E402
from services.cosecha_pago import JORNADA_HORAS, jornada_cells, payable  # noqa: E402


def test_split_day_is_one_jornada_and_projects_to_the_day_pay():
    days = {
        ("2026-10-26", "Ana", "PLP"): {
            "fecha": "2026-10-26",
            "trato": 4000,
            "piso": 2000,
            "por_cuartel": {
                "CC-860 CIRUELOS": {"capachos": 1, "trato": 1000},
                "CC-410 OTRO": {"capachos": 3, "trato": 3000},
            },
        }
    }
    cells = jornada_cells(days)
    assert sum(cell["total_trabajado"] for cell in cells) == 6000
    assert sum(cell["horas_trabajadas"] for cell in cells) == JORNADA_HORAS
    assert {cell["centro_costo"] for cell in cells} == {"860", "410"}
    for cell in cells:
        assert _hora_ponderada_9h(cell["total_trabajado"], cell["horas_trabajadas"]) == 6000


def test_floor_only_week_projects_to_the_daily_floor():
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
            rows = _load_hora_ponderada_rows(
                cur,
                "2026-10-26",
                "2026-10-27",
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
                None,
                "COSECHA",
            )
            other_labor = _load_hora_ponderada_rows(
                cur,
                "2026-10-26",
                "2026-10-27",
                "SERVICIOS AGRICOLAS PLP SPA",
                "ZUÑIGA",
                None,
                "PODA",
            )
    finally:
        conn.close()

    paid = [row for row in data["personas_dias"] if row["a_pagar"]]
    assert paid
    assert sum(cell["total_trabajado"] for cell in data["celdas"]) == sum(
        row["a_pagar"] for row in paid
    )
    assert sum(cell["horas_trabajadas"] for cell in data["celdas"]) == len(paid) * JORNADA_HORAS
    assert rows
    assert all(row["labor"] == "COSECHA" for row in rows)
    assert all(
        _hora_ponderada_9h(row["total_trabajado"], row["horas_trabajadas"]) is not None
        for row in rows
    )
    # A day where every person earned the same amount projects to that amount
    # on every cost center. 2026-10-26 is the floor-only day ($22.000).
    by_date: dict[str, set] = {}
    for person in paid:
        by_date.setdefault(person["fecha"], set()).add(person["a_pagar"])
    flat_days = {fecha: next(iter(pays)) for fecha, pays in by_date.items() if len(pays) == 1}
    assert flat_days
    for row in rows:
        if row["fecha"] in flat_days:
            assert (
                _hora_ponderada_9h(row["total_trabajado"], row["horas_trabajadas"])
                == flat_days[row["fecha"]]
            )
    assert all(row["labor"] != "COSECHA" for row in other_labor)
