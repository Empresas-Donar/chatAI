"""Worker trace keeps harvest scans when the QR credential is gone."""

import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.cosecha_trazabilidad import SearchTooShort, list_workers, search_workers  # noqa: E402


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


def test_worker_picker_lists_juan_once(cur):
    data = list_workers(cur)
    matches = [row for row in data["trabajadores"] if "28909047" in (row["rut"] or "")]
    assert len(matches) == 1
    juan = matches[0]
    assert juan["capachos"] >= 52
    assert juan["dias_trabajados"] >= 4
    assert juan["cuadrilla"] == "2"
    assert juan["contratista"] == "PLP"
    assert fold_name(juan["nombre"]) == "JUAN ANGULO"


def fold_name(value):
    return " ".join((value or "").upper().split())


def test_filters_keep_only_the_window(cur):
    listed = list_workers(
        cur,
        empresa="ZUÑIGA",
        contratista="SERVICIOS AGRICOLAS PLP SPA",
        desde="2026-10-28",
        hasta="2026-10-30",
    )
    juan = next(row for row in listed["trabajadores"] if "28909047" in (row["rut"] or ""))
    assert juan["dias_trabajados"] == 3
    assert juan["capachos"] >= 47
    assert all("PLP" in fold_name(row["contratista"]) for row in listed["trabajadores"])

    outside = search_workers(
        cur,
        "28909047-9",
        empresa="ZUÑIGA",
        contratista="PLP",
        desde="2026-10-21",
        hasta="2026-10-27",
    )
    assert outside["personas"] == []

    window = search_workers(
        cur,
        "juan angulo",
        desde="2026-10-28",
        hasta="2026-10-30",
        contratista="PLP",
    )
    person = next(row for row in window["personas"] if "28909047" in row["rut"])
    assert person["dias_trabajados"] == 3
    assert {day["fecha"] for day in person["dias"]} == {"2026-10-28", "2026-10-29", "2026-10-30"}

    other_farm = list_workers(cur, empresa="Isla de Maipo", desde="2026-10-28", hasta="2026-10-30")
    assert other_farm["trabajadores"] == []


def test_short_query_is_rejected():
    with pytest.raises(SearchTooShort):
        search_workers(None, "ju")


def test_juan_angulo_scans_remain_when_the_credential_is_gone(cur):
    data = search_workers(cur, "juan angulo")
    person = next(row for row in data["personas"] if "28909047" in row["rut"])
    assert person["capachos"] == len(person["escaneos"])
    assert person["capachos"] >= 52
    assert "PLP" in person["contratistas"]
    assert person["cuadrillas_trabajadas"] == 1
    assert person["dias_trabajados"] == len(person["dias"])
    assert person["dias_trabajados"] >= 4
    assert "2" in person["cuadrillas"]
    assert person["qrs_usados"] == 2
    assert {qr["codigo_qr"] for qr in person["qrs"]} == {"cos;AAAF1380", "cos;AAAF1313"}
    assert sum(qr["capachos"] for qr in person["qrs"]) == person["capachos"]
    assert any(scan["fecha"] == "2026-10-20" for scan in person["escaneos"])
    assert any(scan["fecha"] == "2026-10-30" for scan in person["escaneos"])
    assert person["nombres"]
    assert person["credencial_vigente"] is False
    assert any("no está en el catálogo" in note for note in person["alertas"])
    assert sum(day["capachos"] for day in person["dias"]) == person["capachos"]
    assert person["a_pagar"] == sum(day["a_pagar"] for day in person["dias"])


def test_rut_finds_the_same_person(cur):
    by_name = search_workers(cur, "juan angulo")
    by_rut = search_workers(cur, "28909047-9")
    name_hit = next(row for row in by_name["personas"] if "28909047" in row["rut"])
    rut_hit = next(row for row in by_rut["personas"] if "28909047" in row["rut"])
    assert rut_hit["capachos"] == name_hit["capachos"]


def test_current_credential_stays_visible(cur):
    data = search_workers(cur, "alina calderon")
    assert len(data["personas"]) == 1
    person = data["personas"][0]
    assert person["capachos"] == len(person["escaneos"])
    assert person["capachos"] > 0
    assert person["credencial_vigente"] is True
    assert person["fichas"]
    assert person["fichas"][0]["contratista"] == "PLP"
