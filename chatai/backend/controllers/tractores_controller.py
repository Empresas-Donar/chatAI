"""
controllers/tractores_controller.py
------------------------------------
Draft catalog of the tractors the tarjas app already uses.

Reads appsheet.tarjas_maquina (patente, año, cumple, color, tractorista,
campo) and the latest Tractorista row in appsheet.tarjas_pagos. The page
does not write: it is a draft to review the fleet.
"""

import datetime
import logging
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg2 import errors
from pydantic import BaseModel

from auth import require_admin, require_auth
from db import get_connection

logger = logging.getLogger("controllers.tractores")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None

_EN_USO_DIAS = 14

_MAQUINAS_SQL = """
SELECT id_maquina, maquina, "año" AS anio, cumple, color, patente,
       tractorista, campo
FROM appsheet.tarjas_maquina
"""

# tarjas_pagos.fecha is text "MM/DD/YYYY HH:MM:SS" (AppSheet). Shown as DD/MM/YYYY.
_USO_SQL = """
SELECT btrim(maquina) AS maquina,
       COUNT(*)::int AS registros,
       MIN(to_date(left(fecha, 10), 'MM/DD/YYYY')) AS desde,
       MAX(to_date(left(fecha, 10), 'MM/DD/YYYY')) AS hasta
FROM appsheet.tarjas_pagos
WHERE lower(btrim(COALESCE(tipo_pago, ''))) = 'tractorista'
  AND btrim(COALESCE(maquina, '')) <> ''
  AND fecha ~ '^\\d{2}/\\d{2}/\\d{4}'
GROUP BY 1
"""

_ULTIMO_SQL = """
SELECT DISTINCT ON (btrim(maquina))
       btrim(maquina) AS maquina,
       trabajador,
       contratista,
       nombre_campo,
       to_date(left(fecha, 10), 'MM/DD/YYYY') AS fecha
FROM appsheet.tarjas_pagos
WHERE lower(btrim(COALESCE(tipo_pago, ''))) = 'tractorista'
  AND btrim(COALESCE(maquina, '')) <> ''
  AND fecha ~ '^\\d{2}/\\d{2}/\\d{4}'
ORDER BY btrim(maquina), to_date(left(fecha, 10), 'MM/DD/YYYY') DESC
"""

_CAMPOS_SQL = """
SELECT id_campo, nombre
FROM appsheet.tarjas_campo
ORDER BY id_campo
"""

_CONDUCTORES_SQL = """
SELECT DISTINCT btrim(maquina) AS maquina,
       btrim(trabajador) AS trabajador
FROM appsheet.tarjas_pagos
WHERE lower(btrim(COALESCE(tipo_pago, ''))) = 'tractorista'
  AND btrim(COALESCE(maquina, '')) <> ''
  AND btrim(COALESCE(trabajador, '')) <> ''
"""

# Same carnet amount as appsheet.costo_tractorista. It is not a column.
_CARNET_CLP = 6000

_JORNADA_SQL = """
SELECT CASE WHEN valor_c_operador_lunes_viernes ~ '^[0-9]+(\\.[0-9]+)?$'
            THEN valor_c_operador_lunes_viernes::numeric END AS con_operador,
       CASE WHEN valor_s_operador_lunes_viernes ~ '^[0-9]+(\\.[0-9]+)?$'
            THEN valor_s_operador_lunes_viernes::numeric END AS sin_operador,
       CASE WHEN "valor_c_Operador_lunes_sabado" ~ '^[0-9]+(\\.[0-9]+)?$'
            THEN "valor_c_Operador_lunes_sabado"::numeric END AS con_sabado,
       CASE WHEN valor_s_operador_lunes_sabado ~ '^[0-9]+(\\.[0-9]+)?$'
            THEN valor_s_operador_lunes_sabado::numeric END AS sin_sabado
FROM appsheet.tarjas_labor
WHERE lower(btrim(nombre)) = 'jornada tractor normal'
  AND lower(btrim(COALESCE(tipo, ''))) = 'tractorista'
ORDER BY id_labor
LIMIT 1
"""

_PERFILES_SQL = """
SELECT id, trabajador, desde, hasta, esquema, con_operador, carnet,
       costo_9h, costo_75
FROM appsheet.tarjas_esquema_tractorista
ORDER BY trabajador, desde
"""

_NOMBRES_SQL = """
SELECT DISTINCT btrim(trabajador) AS trabajador
FROM appsheet.tarjas_pagos
WHERE lower(btrim(COALESCE(tipo_pago, ''))) = 'tractorista'
  AND btrim(COALESCE(trabajador, '')) <> ''
"""

_ESQUEMA_SQL = """
SELECT trabajador, desde, hasta, esquema, con_operador, carnet
FROM appsheet.tarjas_esquema_tractorista
"""


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def _fmt(day: datetime.date | None) -> str | None:
    if day is None:
        return None
    return f"{day.day:02d}/{day.month:02d}/{day.year}"


def parse_anio(raw: str | None) -> tuple[datetime.date | None, bool]:
    """Return (date, has_day). A bare year is 1 January of that year."""
    text = " ".join((raw or "").split())
    if not text:
        return None, False
    for fmt, precise in (("%d/%m/%Y", True), ("%Y-%m-%d", True), ("%Y", False)):
        try:
            return datetime.datetime.strptime(text, fmt).date(), precise
        except ValueError:
            continue
    return None, False


def antiguedad(day: datetime.date | None, today: datetime.date) -> tuple[int | None, str]:
    if day is None:
        return None, "Sin año"
    years = today.year - day.year - ((today.month, today.day) < (day.month, day.day))
    if years <= 0:
        return 0, "Este año"
    if years == 1:
        return 1, "1 año"
    return years, f"{years} años"


def _key(patente: str, maquina: str) -> str:
    if patente:
        return "P:" + patente.upper()
    return "N:" + " ".join(maquina.split()).upper()


def _blank_group(key: str) -> dict:
    return {
        "id": key,
        "patente": "",
        "maquina": "",
        "anio": None,
        "anio_preciso": False,
        "anio_fecha": None,
        "cumple": "",
        "color": "",
        "tractorista": "",
        "campos": set(),
        "nombres": set(),
        "score": -1,
        "en_catalogo": False,
    }


def _absorb(group: dict, row: dict) -> None:
    patente = " ".join((row.get("patente") or "").split()).upper()
    maquina = " ".join((row.get("maquina") or "").split())
    anio_fecha, preciso = parse_anio(row.get("anio"))
    score = 0
    if patente:
        score += 4
    if preciso:
        score += 2
    elif anio_fecha:
        score += 1
    if (row.get("cumple") or "").strip():
        score += 2
    if (row.get("color") or "").strip():
        score += 1
    if (row.get("tractorista") or "").strip():
        score += 1
    if (row.get("campo") or "").strip():
        score += 1

    if maquina:
        group["nombres"].add(maquina)
    if not group["patente"] and patente:
        group["patente"] = patente
    if maquina and (
        not group["maquina"]
        or (patente and maquina.upper().startswith(patente) and score >= group["score"])
        or (score > group["score"] and not group["maquina"].upper().startswith(group["patente"] or "\0"))
    ):
        group["maquina"] = maquina
    if anio_fecha and (
        group["anio_fecha"] is None
        or (preciso and not group["anio_preciso"])
        or (preciso == group["anio_preciso"] and score >= group["score"])
    ):
        group["anio_fecha"] = anio_fecha
        group["anio_preciso"] = preciso
        group["anio"] = _fmt(anio_fecha) if preciso else str(anio_fecha.year)
    campo = (row.get("campo") or "").strip()
    if campo.isdigit():
        group["campos"].add(int(campo))
    if score >= group["score"]:
        group["score"] = score
        if (row.get("cumple") or "").strip():
            group["cumple"] = row["cumple"].strip().upper()
        if (row.get("color") or "").strip():
            group["color"] = row["color"].strip()
        if (row.get("tractorista") or "").strip():
            group["tractorista"] = row["tractorista"].strip()
    group["en_catalogo"] = True


def _uso_de(group: dict, uso: dict, ultimo: dict) -> dict | None:
    hit = None
    for nombre in group["nombres"]:
        if nombre in uso:
            row = uso[nombre]
            if hit is None or (row["hasta"] or datetime.date.min) > (hit["hasta"] or datetime.date.min):
                hit = row
    if hit is None and group["patente"]:
        for nombre, row in uso.items():
            if nombre.upper().startswith(group["patente"]):
                if hit is None or (row["hasta"] or datetime.date.min) > (hit["hasta"] or datetime.date.min):
                    hit = row
    if hit is None:
        return None
    last = ultimo.get(hit["maquina"], {})
    return {**hit, **last}


def _nombres_pago(group: dict, nombres: set[str]) -> list[str]:
    hits = [nombre for nombre in nombres if nombre in group["nombres"]]
    if hits or not group["patente"]:
        return hits
    return [nombre for nombre in nombres if nombre.upper().startswith(group["patente"])]


def _esquema_vigente(esquemas: list[dict], trabajador: str, today: datetime.date) -> dict | None:
    vigentes = [
        row for row in esquemas
        if row["trabajador"] == trabajador
        and row["desde"] <= today
        and (row["hasta"] is None or row["hasta"] >= today)
    ]
    if not vigentes:
        return None
    return max(vigentes, key=lambda row: row["desde"])


def _licencia(esquema: dict | None) -> dict:
    """Carnet is the driver's row, not the tractor. Missing row assumes carnet."""
    if esquema is None:
        return {
            "carnet": None,
            "etiqueta": "Sin ficha",
            "aviso": "No tiene ficha de horario. Se cobra como con carnet.",
        }
    if not esquema["con_operador"]:
        return {
            "carnet": False,
            "etiqueta": "Sin operador",
            "aviso": None,
        }
    if esquema["carnet"]:
        return {"carnet": True, "etiqueta": "Con carnet", "aviso": None}
    return {
        "carnet": False,
        "etiqueta": "Sin carnet",
        "aviso": "Sin carnet: la jornada normal no suma los $6.000.",
    }


def _jornada(base: Decimal, horas: Decimal, jornada: Decimal, con_carnet: bool) -> int:
    amount = base + (_CARNET_CLP if con_carnet else 0)
    if horas < jornada:
        amount = (amount * horas / jornada).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(amount)


def tarifa_uso(con_operador, sin_operador, con_sabado, sin_sabado) -> dict:
    """Price of one normal shift. Carnet only changes the with-operator rate."""
    nueve = Decimal(9)
    siete = Decimal("7.5")
    con = Decimal(con_operador)
    sin = Decimal(sin_operador)
    sab = Decimal(con_sabado if con_sabado is not None else con_operador)
    sab_sin = Decimal(sin_sabado if sin_sabado is not None else sin_operador)
    return {
        "carnet": _CARNET_CLP,
        "con_carnet_9h": _jornada(con, nueve, nueve, True),
        "sin_carnet_9h": _jornada(con, nueve, nueve, False),
        "con_carnet_75": _jornada(con, siete, nueve, True),
        "sin_carnet_75": _jornada(con, siete, nueve, False),
        "sin_operador_9h": _jornada(sin, nueve, nueve, False),
        "sin_operador_75": _jornada(sin, siete, nueve, False),
        "con_carnet_sab": int(sab) + _CARNET_CLP,
        "sin_carnet_sab": int(sab),
        "sin_operador_sab": int(sab_sin),
    }


def estandar_jornada(carnet: bool, con_operador: bool, esquema: str, tarifa: dict) -> tuple[int, int]:
    if esquema == "lun_sab":
        if not con_operador:
            return tarifa["sin_operador_9h"], tarifa["sin_operador_sab"]
        if carnet:
            return tarifa["con_carnet_9h"], tarifa["con_carnet_sab"]
        return tarifa["sin_carnet_9h"], tarifa["sin_carnet_sab"]
    if not con_operador:
        return tarifa["sin_operador_9h"], tarifa["sin_operador_75"]
    if carnet:
        return tarifa["con_carnet_9h"], tarifa["con_carnet_75"]
    return tarifa["sin_carnet_9h"], tarifa["sin_carnet_75"]


def _attach(group: dict, conductores: list[dict], esquemas: list[dict], today: datetime.date) -> dict:
    nombres = {row["maquina"] for row in conductores}
    propios = set(_nombres_pago(group, nombres))
    personas = []
    for row in conductores:
        if row["maquina"] not in propios:
            continue
        if any(persona["nombre"] == row["trabajador"] for persona in personas):
            continue
        licencia = _licencia(_esquema_vigente(esquemas, row["trabajador"], today))
        personas.append({
            "nombre": row["trabajador"],
            "licencia": licencia["etiqueta"],
            "carnet": licencia["carnet"],
            "aviso": licencia["aviso"],
        })
    personas.sort(key=lambda row: row["nombre"])

    avisos = []
    for persona in personas:
        if persona["aviso"] and persona["aviso"] not in avisos:
            avisos.append(persona["aviso"])
    cumple = (group.get("cumple") or "").upper()
    if cumple == "NO" and any(row["carnet"] for row in personas):
        avisos.append("Este tractor no cumple. Igual, si el conductor tiene carnet, la jornada se cobra con carnet.")
    if cumple == "SI" and any(row["licencia"] == "Sin carnet" for row in personas):
        avisos.append("Este tractor cumple, pero hay un conductor sin carnet. Su jornada se cobra sin carnet.")
    return {"conductores": personas, "avisos": avisos}


def build_tractores(
    maquinas: list[dict],
    uso_rows: list[dict],
    ultimo_rows: list[dict],
    campos: list[dict],
    conductores: list[dict],
    esquemas: list[dict],
    today: datetime.date,
) -> list[dict]:
    groups: dict[str, dict] = {}
    nameless = []
    for row in maquinas:
        patente = " ".join((row.get("patente") or "").split()).upper()
        maquina = " ".join((row.get("maquina") or "").split())
        if not patente and not maquina:
            continue
        if not patente:
            nameless.append(row)
            continue
        key = _key(patente, maquina)
        group = groups.get(key)
        if group is None:
            group = _blank_group(key)
            groups[key] = group
        _absorb(group, row)

    for row in nameless:
        maquina = " ".join((row.get("maquina") or "").split())
        upper = maquina.upper()
        match = next(
            (group for group in groups.values()
             if group["patente"] and upper.startswith(group["patente"])),
            None,
        )
        if match is not None:
            _absorb(match, row)
            continue
        key = _key("", maquina)
        group = groups.get(key)
        if group is None:
            group = _blank_group(key)
            groups[key] = group
        _absorb(group, row)

    uso = {row["maquina"]: row for row in uso_rows}
    ultimo = {row["maquina"]: row for row in ultimo_rows}
    campo_nombre = {int(c["id_campo"]): c["nombre"] for c in campos}

    claimed = set()
    for group in groups.values():
        found = _uso_de(group, uso, ultimo)
        if found:
            claimed.add(found["maquina"])
            group["_uso"] = found

    for nombre, row in uso.items():
        if nombre in claimed:
            continue
        key = _key("", nombre)
        group = _blank_group(key)
        group["maquina"] = nombre
        group["nombres"].add(nombre)
        group["_uso"] = {**row, **ultimo.get(nombre, {})}
        groups[key] = group

    limite = today - datetime.timedelta(days=_EN_USO_DIAS)
    out = []
    for group in groups.values():
        years, label = antiguedad(group["anio_fecha"], today)
        found = group.get("_uso") or {}
        hasta = found.get("fecha") or found.get("hasta")
        if hasta is None:
            estado, estado_label = "sin_tarjas", "Sin uso"
        elif hasta >= limite:
            estado, estado_label = "en_uso", "En uso"
        else:
            estado, estado_label = "quieto", "Quieto"
        extra = _attach(group, conductores, esquemas, today)
        extra.pop("_nombres", None)
        out.append({
            "id": group["id"],
            "patente": group["patente"] or None,
            "maquina": group["maquina"],
            "anio": group["anio"],
            "antiguedad": label,
            "anios": years,
            "cumple": group["cumple"] or None,
            "color": group["color"] or None,
            "tractorista": group["tractorista"] or None,
            "campos": [
                {"id_campo": cid, "nombre": campo_nombre.get(cid, str(cid))}
                for cid in sorted(group["campos"])
            ],
            "registros": int(found.get("registros") or 0),
            "desde": _fmt(found.get("desde")),
            "ultima_tarja": _fmt(hasta),
            "trabajador": found.get("trabajador") or None,
            "contratista": found.get("contratista") or None,
            "campo_tarja": found.get("nombre_campo") or None,
            "estado": estado,
            "estado_label": estado_label,
            "en_catalogo": group["en_catalogo"],
            **extra,
        })
    out.sort(key=lambda row: (
        {"en_uso": 0, "quieto": 1, "sin_tarjas": 2}[row["estado"]],
        -(datetime.datetime.strptime(row["ultima_tarja"], "%d/%m/%Y").toordinal()
          if row["ultima_tarja"] else 0),
        row["maquina"],
    ))
    return out


def _connect():
    try:
        return get_connection()
    except Exception:
        logger.exception("tractores: DB connect failed")
        raise


@router.get("/utilidades/tractores", response_class=HTMLResponse)
async def tractores_page(request: Request, _admin=Depends(require_admin)):
    return _templates.TemplateResponse(request, "tractores.html")


@router.get("/api/tractores")
async def list_tractores(_admin=Depends(require_admin)):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_MAQUINAS_SQL)
            cols = [d[0] for d in cur.description]
            maquinas = [dict(zip(cols, rec)) for rec in cur.fetchall()]
            cur.execute(_USO_SQL)
            cols = [d[0] for d in cur.description]
            uso = [dict(zip(cols, rec)) for rec in cur.fetchall()]
            cur.execute(_ULTIMO_SQL)
            cols = [d[0] for d in cur.description]
            ultimo = [dict(zip(cols, rec)) for rec in cur.fetchall()]
            cur.execute(_CAMPOS_SQL)
            campos = [{"id_campo": rec[0], "nombre": rec[1]} for rec in cur.fetchall()]
            cur.execute(_CONDUCTORES_SQL)
            cols = [d[0] for d in cur.description]
            conductores = [dict(zip(cols, rec)) for rec in cur.fetchall()]
            cur.execute(_ESQUEMA_SQL)
            cols = [d[0] for d in cur.description]
            esquemas = [dict(zip(cols, rec)) for rec in cur.fetchall()]
            cur.execute(_JORNADA_SQL)
            jornada = cur.fetchone()
        today = datetime.date.today()
        rows = build_tractores(
            maquinas, uso, ultimo, campos, conductores, esquemas, today
        )
        tarifa = _tarifa_de(jornada)
        return {"tractores": rows, "campos": campos, "hoy": _fmt(today), "tarifa": tarifa}
    finally:
        conn.close()


def _tarifa_de(jornada) -> dict | None:
    if not jornada or jornada[0] is None or jornada[1] is None:
        return None
    return tarifa_uso(jornada[0], jornada[1], jornada[2], jornada[3])


def _parse_fecha(value: str | None, required: bool) -> datetime.date | None:
    text = (value or "").strip()
    if not text:
        if required:
            raise HTTPException(status_code=422, detail="La fecha de inicio es obligatoria.")
        return None
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        day, month, year = (int(part) for part in match.groups())
    else:
        iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
        if not iso:
            raise HTTPException(status_code=422, detail="La fecha es DD/MM/YYYY.")
        year, month, day = (int(part) for part in iso.groups())
    try:
        return datetime.date(year, month, day)
    except ValueError:
        raise HTTPException(status_code=422, detail="La fecha no existe.")


def _parse_monto(value, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise HTTPException(status_code=422, detail=f"El {label} no es un monto.")
    if isinstance(value, int):
        amount = value
    else:
        digits = re.sub(r"[^\d]", "", str(value))
        if not digits:
            raise HTTPException(status_code=422, detail=f"El {label} no es un monto.")
        amount = int(digits)
    if amount < 0 or amount > 1_000_000:
        raise HTTPException(status_code=422, detail=f"El {label} tiene que ser un monto en pesos.")
    return amount


def _perfil_id(nombre: str, desde: datetime.date) -> str:
    plain = unicodedata.normalize("NFD", nombre).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:40] or "conductor"
    return f"{slug}-{desde.isoformat()}"


class ConductorIn(BaseModel):
    trabajador: str | None = None
    carnet: bool
    con_operador: bool
    esquema: str
    desde: str
    hasta: str | None = None
    costo_9h: int | None = None
    costo_75: int | None = None


def _clean_perfil(body: ConductorIn, tarifa: dict, nombre: str | None = None) -> dict:
    trabajador = " ".join((nombre if nombre is not None else body.trabajador or "").split())
    if not trabajador:
        raise HTTPException(status_code=422, detail="El nombre es obligatorio.")
    if len(trabajador) > 120:
        raise HTTPException(status_code=422, detail="El nombre es demasiado largo.")
    if body.esquema not in ("lun_vie", "lun_sab"):
        raise HTTPException(status_code=422, detail="El horario es lunes a viernes o lunes a sábado.")
    desde = _parse_fecha(body.desde, required=True)
    hasta = _parse_fecha(body.hasta, required=False)
    if hasta and hasta < desde:
        raise HTTPException(status_code=422, detail="La fecha de término es anterior al inicio.")
    estandar_9, estandar_75 = estandar_jornada(
        body.carnet, body.con_operador, body.esquema, tarifa
    )
    costo_9 = _parse_monto(body.costo_9h, "costo de 9 h")
    costo_75 = _parse_monto(body.costo_75, "costo de 7,5 h")
    if body.esquema == "lun_sab":
        costo_9 = None
    if costo_9 == estandar_9:
        costo_9 = None
    if costo_75 == estandar_75:
        costo_75 = None
    return {
        "trabajador": trabajador,
        "carnet": body.carnet,
        "con_operador": body.con_operador,
        "esquema": body.esquema,
        "desde": desde,
        "hasta": hasta,
        "costo_9h": costo_9,
        "costo_75": costo_75,
    }


def _publico_perfil(row: dict | None, tarifa: dict, nombre: str, en_ficha: bool) -> dict:
    if row is None:
        estandar_9, estandar_75 = estandar_jornada(True, True, "lun_vie", tarifa)
        return {
            "id": None,
            "trabajador": nombre,
            "carnet": None,
            "con_operador": True,
            "esquema": "lun_vie",
            "horario": "Lunes a viernes",
            "licencia": "Sin ficha",
            "desde": None,
            "hasta": None,
            "jornada_9h": estandar_9,
            "jornada_75": estandar_75,
            "costo_9h": None,
            "costo_75": None,
            "en_ficha": False,
        }
    carnet = bool(row["carnet"])
    con_operador = bool(row["con_operador"])
    esquema = row["esquema"]
    estandar_9, estandar_75 = estandar_jornada(carnet, con_operador, esquema, tarifa)
    costo_9 = int(row["costo_9h"]) if row["costo_9h"] is not None else None
    costo_75 = int(row["costo_75"]) if row["costo_75"] is not None else None
    if not con_operador:
        licencia = "Sin operador"
    elif carnet:
        licencia = "Con carnet"
    else:
        licencia = "Sin carnet"
    return {
        "id": row["id"],
        "trabajador": row["trabajador"],
        "carnet": carnet,
        "con_operador": con_operador,
        "esquema": esquema,
        "horario": "Lunes a sábado" if esquema == "lun_sab" else "Lunes a viernes",
        "licencia": licencia,
        "desde": _fmt(row["desde"]),
        "hasta": _fmt(row["hasta"]),
        "jornada_9h": costo_9 if costo_9 is not None else estandar_9,
        "jornada_75": costo_75 if costo_75 is not None else estandar_75,
        "costo_9h": costo_9,
        "costo_75": costo_75,
        "en_ficha": en_ficha,
    }


def _perfiles(cur, today: datetime.date) -> tuple[list[dict], dict | None]:
    cur.execute(_PERFILES_SQL)
    cols = [d[0] for d in cur.description]
    filas = [dict(zip(cols, rec)) for rec in cur.fetchall()]
    cur.execute(_NOMBRES_SQL)
    nombres = [rec[0] for rec in cur.fetchall()]
    cur.execute(_JORNADA_SQL)
    tarifa = _tarifa_de(cur.fetchone())
    if tarifa is None:
        raise HTTPException(status_code=422, detail="No está la tarifa de la jornada normal.")
    vigente: dict[str, dict] = {}
    for row in filas:
        if row["desde"] <= today and (row["hasta"] is None or row["hasta"] >= today):
            actual = vigente.get(row["trabajador"])
            if actual is None or row["desde"] > actual["desde"]:
                vigente[row["trabajador"]] = row
    vistos = set(vigente)
    perfiles = [
        _publico_perfil(row, tarifa, row["trabajador"], True)
        for row in sorted(vigente.values(), key=lambda item: item["trabajador"])
    ]
    for nombre in sorted(nombres):
        if nombre not in vistos:
            perfiles.append(_publico_perfil(None, tarifa, nombre, False))
    return perfiles, tarifa


@router.get("/api/conductores")
async def list_conductores(_admin=Depends(require_admin)):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            perfiles, tarifa = _perfiles(cur, datetime.date.today())
        return {"conductores": perfiles, "tarifa": tarifa}
    finally:
        conn.close()


@router.post("/api/conductores")
async def create_conductor(body: ConductorIn, _admin=Depends(require_admin)):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            _, tarifa = _perfiles(cur, datetime.date.today())
            data = _clean_perfil(body, tarifa)
            cur.execute(
                """
                SELECT 1 FROM appsheet.tarjas_esquema_tractorista
                WHERE trabajador = %s
                  AND desde <= %s
                  AND (hasta IS NULL OR hasta >= %s)
                """,
                (data["trabajador"], data["desde"], data["desde"]),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Ese conductor ya tiene una ficha vigente.")
            nuevo = _perfil_id(data["trabajador"], data["desde"])
            cur.execute(
                """
                INSERT INTO appsheet.tarjas_esquema_tractorista
                    (id, trabajador, desde, hasta, esquema, con_operador, carnet, costo_9h, costo_75)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    nuevo, data["trabajador"], data["desde"], data["hasta"], data["esquema"],
                    data["con_operador"], data["carnet"], data["costo_9h"], data["costo_75"],
                ),
            )
        conn.commit()
        return {"id": nuevo}
    except errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una ficha con ese nombre y esa fecha.")
    finally:
        conn.close()


@router.patch("/api/conductores/{perfil_id}")
async def update_conductor(perfil_id: str, body: ConductorIn, _admin=Depends(require_admin)):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trabajador FROM appsheet.tarjas_esquema_tractorista
                WHERE id = %s
                """,
                (perfil_id,),
            )
            found = cur.fetchone()
            if not found:
                raise HTTPException(status_code=404, detail="No está esa ficha.")
            _, tarifa = _perfiles(cur, datetime.date.today())
            data = _clean_perfil(body, tarifa, nombre=found[0])
            cur.execute(
                """
                UPDATE appsheet.tarjas_esquema_tractorista
                   SET desde = %s, hasta = %s, esquema = %s,
                       con_operador = %s, carnet = %s,
                       costo_9h = %s, costo_75 = %s
                 WHERE id = %s
                """,
                (
                    data["desde"], data["hasta"], data["esquema"],
                    data["con_operador"], data["carnet"],
                    data["costo_9h"], data["costo_75"], perfil_id,
                ),
            )
        conn.commit()
        return {"id": perfil_id}
    except errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una ficha con ese nombre y esa fecha.")
    finally:
        conn.close()
