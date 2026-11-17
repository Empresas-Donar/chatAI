"""Enabled tractor ficha: validation, grouping, and a rolled-back write."""

import datetime
import os
import sys

import psycopg2
import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from controllers.tractores_controller import (  # noqa: E402
    TractorIn,
    build_tractores,
    clean_tractor,
    write_tractor,
)

_CAMPOS = {1, 2, 3, 4}
_TODAY = datetime.date(2026, 11, 17)


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
    conn.autocommit = False
    cursor = conn.cursor()
    try:
        yield cursor
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def _body(**overrides):
    data = {
        "patente": "ZZTT99",
        "maquina": "ZZTT99-Same 90",
        "modelo": "Same Frutteto 90",
        "color": "ROJO",
        "chasis": "ZKDCL999W0RS99999",
        "anio": 2024,
        "fecha_partida": "01/02/2024",
        "cumple": "SI",
        "tractorista": "RD",
        "campos": [1, 2],
        "habilitado": True,
    }
    data.update(overrides)
    return TractorIn(**data)


def test_clean_keeps_the_ficha_fields():
    cleaned = clean_tractor(_body(patente=" zztt99 "), _CAMPOS)
    assert cleaned["patente"] == "ZZTT99"
    assert cleaned["chasis"] == "ZKDCL999W0RS99999"
    assert cleaned["anio"] == 2024
    assert cleaned["fecha_partida"] == datetime.date(2024, 2, 1)
    assert cleaned["campos"] == ["1", "2"]
    assert cleaned["habilitado"] is True


def test_clean_rejects_a_chasis_with_spaces():
    with pytest.raises(HTTPException) as bad:
        clean_tractor(_body(chasis="ZK DC"), _CAMPOS)
    assert bad.value.status_code == 422


def test_clean_requires_a_campo():
    with pytest.raises(HTTPException) as bad:
        clean_tractor(_body(campos=[]), _CAMPOS)
    assert bad.value.status_code == 422


def test_age_uses_fecha_partida_when_the_model_year_differs():
    rows = build_tractores(
        maquinas=[{
            "maquina": "VPYY10-Same 65",
            "modelo": "Same Frutetto 65",
            "anio": "12/11/2025",
            "anio_modelo": 2026,
            "fecha_partida": datetime.date(2025, 11, 12),
            "cumple": "SI",
            "color": "ROJO",
            "patente": "VPYY10",
            "chasis": "ZKDCK702W0RS10415",
            "tractorista": "RD",
            "campo": "1",
            "habilitado": True,
        }],
        uso_rows=[],
        ultimo_rows=[],
        campos=[{"id_campo": 1, "nombre": "TALAGANTE"}],
        conductores=[],
        esquemas=[],
        today=_TODAY,
    )
    assert len(rows) == 1
    assert rows[0]["anio_modelo"] == 2026
    assert rows[0]["fecha_partida"] == "12/11/2025"
    assert rows[0]["antiguedad"] == "1 año"
    assert rows[0]["habilitado"] is True


def test_two_campos_stay_on_one_tractor():
    base = {
        "maquina": "VDCW81-Same 80.4",
        "modelo": "Same frutteto 80.4",
        "anio": "01/01/2024",
        "anio_modelo": 2024,
        "fecha_partida": datetime.date(2024, 1, 1),
        "cumple": "SI",
        "color": "ROJO",
        "patente": "VDCW81",
        "chasis": "ZKDCL302W0RS10554",
        "tractorista": "RD",
        "habilitado": True,
    }
    rows = build_tractores(
        maquinas=[{**base, "campo": "1"}, {**base, "campo": "2"}],
        uso_rows=[],
        ultimo_rows=[],
        campos=[
            {"id_campo": 1, "nombre": "TALAGANTE"},
            {"id_campo": 2, "nombre": "ISLA DE MAIPO"},
        ],
        conductores=[],
        esquemas=[],
        today=_TODAY,
    )
    assert len(rows) == 1
    assert [campo["nombre"] for campo in rows[0]["campos"]] == [
        "TALAGANTE",
        "ISLA DE MAIPO",
    ]
    assert rows[0]["chasis"] == "ZKDCL302W0RS10554"


def test_enabled_fleet_is_stored(cur):
    cur.execute(
        """
        SELECT upper(btrim(patente)) AS patente,
               array_agg(btrim(campo) ORDER BY btrim(campo)) AS campos,
               max(chasis) AS chasis,
               max(anio) AS anio,
               max(fecha_partida) AS fecha,
               bool_or(habilitado) AS habilitado
        FROM appsheet.tarjas_maquina
        WHERE upper(btrim(coalesce(patente, ''))) IN
              ('VPYY10','PTFK72','PZVS78','RLXJ64','RXZS88','VDCW81','TZHH19')
        GROUP BY 1
        ORDER BY 1
        """
    )
    found = {row[0]: row for row in cur.fetchall()}
    assert set(found) == {
        "VPYY10", "PTFK72", "PZVS78", "RLXJ64", "RXZS88", "VDCW81", "TZHH19",
    }
    assert list(found["RXZS88"][1]) == ["1", "2"]
    assert list(found["VDCW81"][1]) == ["1", "2"]
    assert found["VPYY10"][2] == "ZKDCK702W0RS10415"
    assert found["VPYY10"][3] == 2026
    assert found["VPYY10"][4] == datetime.date(2025, 11, 12)
    assert found["RLXJ64"][3] == 2022
    assert found["RLXJ64"][4] == datetime.date(2021, 11, 8)
    assert all(row[5] for row in found.values())


def test_write_roundtrip_rolls_back(cur):
    data = clean_tractor(_body(), _CAMPOS)
    write_tractor(cur, data, None)
    cur.execute(
        """
        SELECT campo, modelo, chasis, anio, fecha_partida, habilitado, "año"
        FROM appsheet.tarjas_maquina
        WHERE upper(btrim(patente)) = 'ZZTT99'
        ORDER BY campo
        """
    )
    rows = cur.fetchall()
    assert [row[0] for row in rows] == ["1", "2"]
    assert rows[0][1] == "Same Frutteto 90"
    assert rows[0][2] == "ZKDCL999W0RS99999"
    assert rows[0][3] == 2024
    assert rows[0][4] == datetime.date(2024, 2, 1)
    assert rows[0][5] is True
    assert rows[0][6] == "01/02/2024"

    data["campos"] = ["1"]
    data["chasis"] = "ZKDCL999W0RS99998"
    write_tractor(cur, data, "ZZTT99")
    cur.execute(
        """
        SELECT campo, chasis FROM appsheet.tarjas_maquina
        WHERE upper(btrim(patente)) = 'ZZTT99'
        ORDER BY campo
        """
    )
    left = cur.fetchall()
    assert left == [("1", "ZKDCL999W0RS99998")]
