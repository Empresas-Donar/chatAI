"""Harvest pay for the tarjas payment reports.

Read-only. One capacho is one scan: the piece rate is the sum of
precio_trato_aplicado, and the daily floor is added once per person and
day. Nothing here is multiplied by the tarjas company factors.
"""

from __future__ import annotations

import datetime

from services.cosecha_rendimiento import _money, amount_due, predios_for_empresa

TIPO = "Cosecha"
# Same tipo strings as tarjas, so harvest folds into those rows.
TIPO_TRATO = "trato"
TIPO_AL_DIA = "Al dia"
LABOR = "COSECHA"


def _empty() -> dict:
    return {
        "es_cosecha": True,
        "total": 0,
        "trato": 0,
        "piso": 0,
        "capachos": 0,
        "jornadas": 0,
        "personas": 0,
        "promedio_diario": None,
        "lines": [],
        "personas_dias": [],
        "cuarteles_pago": [],
    }


def _iso(value) -> str:
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)[:10]


def _split_int(total: int, weights: list[int]) -> list[int]:
    """Split an integer amount by weights. The parts sum back to total."""
    if not weights:
        return []
    base = sum(weights)
    if base <= 0:
        weights = [1] * len(weights)
        base = len(weights)
    shares = []
    used = 0
    for i, weight in enumerate(weights):
        if i == len(weights) - 1:
            shares.append(total - used)
        else:
            part = total * weight // base
            shares.append(part)
            used += part
    return shares


def _line(tipo_pago, labor, cuartel, qty, total, *, al_dia=False, cultivo="", shares=None):
    """One payable line. qty × unit price equals total when the price is whole."""
    unit = (total / qty) if qty else 0
    if qty and total % qty == 0:
        unit = total // qty
    else:
        unit = round(unit, 2)
    return {
        "tipo_pago": tipo_pago,
        "labor": labor,
        "cuartel": cuartel,
        "cultivo": cultivo,
        "jornadas": qty,
        "total_unitario": unit,
        "total_trabajado": total,
        "total_empresa": total,
        "total_labor": total,
        "es_cosecha": True,
        "al_dia": al_dia,
        "shares": shares or {cuartel: total},
    }


def _document_lines(days: dict) -> list[dict]:
    """Lines shared by the order screen, the PDF and the Odoo file.

    Piece rate is capachos at the price actually scanned. Days with price 0
    are not capachos to bill. The floor is paid once per person-day, and the
    pesos follow the capachos of each registro.
    """
    piece: dict[tuple, dict] = {}
    floors: dict[tuple, dict] = {}
    for day in days.values():
        al_dia = day["trato"] == 0 and day["piso"] > 0
        for cuartel, part in day["por_cuartel"].items():
            for precio, count in part["precios"].items():
                bucket = piece.setdefault(
                    (cuartel, precio),
                    {"cuartel": cuartel, "capachos": 0, "trato": 0},
                )
                bucket["capachos"] += count
                bucket["trato"] += precio * count
        if not day["piso"] or not day["por_cuartel"]:
            continue
        # The trato's daily floor is paid once. Scans still belong to their
        # registro and cuartel, so the amount follows the capachos.
        names = sorted(day["por_cuartel"])
        pesos = _split_int(
            day["piso"], [day["por_cuartel"][name]["capachos"] for name in names]
        )
        tipo = TIPO_AL_DIA if al_dia else TIPO_TRATO
        bucket = floors.setdefault(
            (tipo, day["piso"]),
            {"jornadas": 0, "total": 0, "shares": {}},
        )
        bucket["jornadas"] += 1
        bucket["total"] += day["piso"]
        for name, peso in zip(names, pesos):
            if peso:
                bucket["shares"][name] = bucket["shares"].get(name, 0) + peso

    lines = []
    for key in sorted(piece, key=lambda item: (item[0], item[1] or 0)):
        bucket = piece[key]
        lines.append(
            _line(
                TIPO_TRATO,
                f"{LABOR} · {bucket['cuartel']}",
                bucket["cuartel"],
                bucket["capachos"],
                bucket["trato"],
            )
        )
    for (tipo, _piso) in sorted(floors, key=lambda item: (item[0] == TIPO_AL_DIA, item[1])):
        bucket = floors[(tipo, _piso)]
        al_dia = tipo == TIPO_AL_DIA
        cuarteles = sorted(bucket["shares"])
        lines.append(
            _line(
                tipo,
                f"{LABOR} · al día" if al_dia else f"{LABOR} · piso",
                " / ".join(cuarteles),
                bucket["jornadas"],
                bucket["total"],
                al_dia=al_dia,
                shares=bucket["shares"],
            )
        )
    return lines


def _pay_by_cuartel(days: dict) -> list[dict]:
    """Piece rate stays on its cuartel. The daily floor is split by capachos."""
    buckets: dict[str, dict] = {}
    for day in days.values():
        parts = day["por_cuartel"]
        names = sorted(parts)
        shares = _split_int(day["piso"], [parts[name]["capachos"] for name in names])
        for name, piso_share in zip(names, shares):
            bucket = buckets.setdefault(
                name, {"cuartel": name, "capachos": 0, "jornadas": 0, "total": 0}
            )
            bucket["capachos"] += parts[name]["capachos"]
            bucket["jornadas"] += 1
            bucket["total"] += parts[name]["trato"] + piso_share
    return [buckets[name] for name in sorted(buckets)]


def payable(cur, fecha_inicio, fecha_termino, contratista=None, empresa=None) -> dict:
    """Harvest amount for a tarjas filter.

    Empresa limits the predio: only Zúñiga (or an empty empresa) has scans.
    Contratista matches the tarjas legal name through the intranet link, or
    the short name stored on the harvest contractor.
    """
    if not predios_for_empresa(empresa):
        return _empty()

    sql = """
        SELECT
          COALESCE(e."fecha", e."fecha_y_hora"::date) AS fecha,
          COALESCE(NULLIF(btrim(e."trabajador"), ''), '(sin nombre)') AS trabajador,
          COALESCE(
            NULLIF(btrim(m.nombre), ''),
            NULLIF(btrim(c."contratistas"), ''),
            NULLIF(btrim(e."contratista"), '')
          ) AS contratista,
          NULLIF(btrim(m.nombre_corto), '') AS nombre_corto,
          COALESCE(
            NULLIF(btrim(cu."nombre_cuartel"), ''),
            NULLIF(btrim(e."cuartel"), ''),
            'Sin cuartel'
          ) AS cuartel,
          NULLIF(btrim(cu."cultivo"), '') AS cultivo,
          e."precio_trato_aplicado" AS precio,
          e."piso_aplicado" AS piso
        FROM appsheet.cosecha_zuniga_escaneo e
        LEFT JOIN appsheet.cosecha_zuniga_contratistas c
          ON c."id_contratista" = e."id_contratista"
        LEFT JOIN intranet.contratistas m
          ON m.id_intranet = c."id_intranet_contratistas"
        LEFT JOIN appsheet.cosecha_zuniga_cuarteles cu
          ON cu."id_cuartel" = e."cuartel"
        WHERE COALESCE(e."fecha", e."fecha_y_hora"::date) BETWEEN %s AND %s
    """
    params: list = [fecha_inicio, fecha_termino]
    if contratista:
        sql += """
          AND (
            COALESCE(
              NULLIF(btrim(m.nombre), ''),
              NULLIF(btrim(c."contratistas"), ''),
              NULLIF(btrim(e."contratista"), '')
            ) = %s
            OR lower(btrim(COALESCE(m.nombre_corto, ''))) = lower(btrim(%s))
          )
        """
        params.extend([contratista, contratista])
    cur.execute(sql, params)
    scans = cur.fetchall()
    if not scans:
        return _empty()

    days: dict[tuple, dict] = {}
    for fecha, trabajador, nombre, _corto, cuartel, _cultivo, precio, piso in scans:
        day_key = (_iso(fecha), trabajador, nombre or "")
        day = days.get(day_key)
        if day is None:
            day = {
                "fecha": day_key[0],
                "trabajador": trabajador,
                "contratista": nombre or "",
                "trato": 0,
                "piso": 0,
                "capachos": 0,
                "cuarteles": set(),
                "por_cuartel": {},
            }
            days[day_key] = day
        precio_i = _money(precio)
        day["trato"] += precio_i
        day["piso"] = max(day["piso"], _money(piso))
        day["capachos"] += 1
        if cuartel:
            day["cuarteles"].add(cuartel)
            part = day["por_cuartel"].setdefault(
                cuartel, {"capachos": 0, "trato": 0, "precios": {}}
            )
            part["capachos"] += 1
            part["trato"] += precio_i
            if precio_i:
                part["precios"][precio_i] = part["precios"].get(precio_i, 0) + 1

    personas_dias = []
    for day in days.values():
        pago = amount_due(day["trato"], day["piso"])
        # A harvest day with no piece rate and only the floor is a daily wage.
        al_dia = day["trato"] == 0 and day["piso"] > 0
        personas_dias.append(
            {
                "fecha": day["fecha"],
                "trabajador": day["trabajador"],
                "contratista": day["contratista"],
                "trato": day["trato"],
                "piso": day["piso"],
                "capachos": day["capachos"],
                "a_pagar": pago,
                "cuarteles": sorted(day["cuarteles"]),
                "es_cosecha": True,
                "al_dia": al_dia,
                "tipo_pago": TIPO_AL_DIA if al_dia else TIPO_TRATO,
            }
        )
    personas_dias.sort(key=lambda row: (row["trabajador"], row["fecha"]))

    lines = _document_lines(days)
    piso_trato = sum(row["piso"] for row in personas_dias if not row["al_dia"])
    piso_al_dia = sum(row["piso"] for row in personas_dias if row["al_dia"])

    cuarteles_pago = _pay_by_cuartel(days)
    total = sum(row["a_pagar"] for row in personas_dias)
    jornadas = len(personas_dias)
    pago_al_dia = sum(row["a_pagar"] for row in personas_dias if row["al_dia"])
    jornadas_al_dia = sum(1 for row in personas_dias if row["al_dia"])
    pago_trato = total - pago_al_dia
    jornadas_trato = jornadas - jornadas_al_dia
    return {
        "es_cosecha": True,
        "total": total,
        "trato": sum(row["trato"] for row in personas_dias),
        "piso": piso_trato + piso_al_dia,
        "pago_trato": pago_trato,
        "pago_al_dia": pago_al_dia,
        "jornadas_trato": jornadas_trato,
        "jornadas_al_dia": jornadas_al_dia,
        "capachos": sum(row["capachos"] for row in personas_dias),
        "jornadas": jornadas,
        "personas": len({row["trabajador"] for row in personas_dias}),
        "promedio_diario": round(total / jornadas) if jornadas else None,
        "lines": lines,
        "personas_dias": personas_dias,
        "cuarteles_pago": cuarteles_pago,
    }
