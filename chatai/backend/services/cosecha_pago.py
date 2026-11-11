"""Harvest pay for the tarjas payment reports.

Read-only. One capacho is one scan: the piece rate is the sum of
precio_trato_aplicado, and the daily floor is added once per person and
day. A row in cosecha_zuniga_salidas_trabajador replaces the floor of
that person and date with accion_piso, on every bin. The day pays that
amount once. 0 pays no floor and the capachos stay.
Nothing here is multiplied by the tarjas company factors.
"""

from __future__ import annotations

import datetime
import re

from services.cosecha_rendimiento import (
    _APP_CAMPO,
    _FOLD_FROM,
    _FOLD_TO,
    _TARJAS_CAMPO,
    _money,
    amount_due,
    fold,
    predios_for_empresa,
)

TIPO = "Cosecha"
# Harvest is piece rate. The floor is part of that trato, including a day
# that only paid the floor. It is not the tarjas "Al día" wage.
TIPO_TRATO = "trato"
LABOR = "COSECHA"
# The harvest app does not record hours. The 9h report treats each
# person-day as one standard jornada so the projection can be computed.
JORNADA_HORAS = 9


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
        "celdas": [],
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


def _cc_code(text: str) -> str:
    match = re.search(r"(\d{3})", text or "")
    return match.group(1) if match else ""


def _collapse_lines_by_cc(lines: list[dict]) -> list[dict]:
    """One Cosecha line per cost center. Capachos and the floor add up.

    The quantity is not a single rate, so jornadas and the unit price stay
    empty. The amount is the sum, with no tarjas factor.
    """
    totals: dict[str, int] = {}
    detail: dict[str, dict] = {}
    for line in lines:
        is_floor = (line.get("labor") or "").endswith("· piso")
        for cuartel, pesos in (line.get("shares") or {}).items():
            code = _cc_code(cuartel)
            totals[code] = totals.get(code, 0) + int(pesos)
            bucket = detail.setdefault(code, {"piso": 0, "precios": {}})
            if is_floor:
                bucket["piso"] += int(pesos)
                continue
            qty = int(line.get("jornadas") or 0)
            price = line.get("total_unitario")
            if qty and price is not None:
                key = int(price) if float(price) == int(float(price)) else price
                bucket["precios"][key] = bucket["precios"].get(key, 0) + qty
    collapsed = []
    for code in sorted(totals):
        total = totals[code]
        if not total:
            continue
        row = _line(TIPO_TRATO, LABOR, code, 0, total, shares={code: total})
        row["cc"] = code
        row["jornadas"] = None
        row["total_unitario"] = None
        row["detalle"] = detail.get(code) or {"piso": 0, "precios": {}}
        collapsed.append(row)
    return collapsed


def _document_lines(days: dict) -> list[dict]:
    """Lines shared by the order screen, the PDF and the Odoo file.

    Piece rate is capachos at the price actually scanned. Days with price 0
    are not capachos to bill. The floor is paid once per person-day, and the
    pesos follow the capachos of each registro. Reports then show one
    Cosecha line per cost center.
    """
    piece: dict[tuple, dict] = {}
    floors: dict[int, dict] = {}
    for day in days.values():
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
        # registro and cuartel, so the amount follows the capachos. A day
        # with no capacho price is the same floor, still cosecha a trato.
        names = sorted(day["por_cuartel"])
        pesos = _split_int(
            day["piso"], [day["por_cuartel"][name]["capachos"] for name in names]
        )
        bucket = floors.setdefault(
            day["piso"],
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
    for piso in sorted(floors):
        bucket = floors[piso]
        cuarteles = sorted(bucket["shares"])
        lines.append(
            _line(
                TIPO_TRATO,
                f"{LABOR} · piso",
                " / ".join(cuarteles),
                bucket["jornadas"],
                bucket["total"],
                shares=bucket["shares"],
            )
        )
    return _collapse_lines_by_cc(lines)


def jornada_cells(days: dict) -> list[dict]:
    """One row per date and cost center for the 9-hour projection.

    Each person-day is JORNADA_HORAS. Those hours follow the pesos: the
    capacho pay stays on its cuartel and the floor is split by capachos,
    the same way as the payable lines. A day on two cuarteles is not two
    jornadas. With hours proportional to the pay, the 9h cell is that
    day's pay (the average, when several people share the cell).
    """
    buckets: dict[tuple, dict] = {}
    for day in days.values():
        pago = amount_due(day["trato"], day["piso"])
        parts = day.get("por_cuartel") or {}
        if pago <= 0 or not parts:
            continue
        names = sorted(parts)
        piso_shares = _split_int(day["piso"], [parts[name]["capachos"] for name in names])
        weighted = []
        for name, piso_share in zip(names, piso_shares):
            pesos = parts[name]["trato"] + piso_share
            if pesos > 0:
                weighted.append((name, pesos))
        if not weighted:
            continue
        assigned = 0.0
        for index, (name, pesos) in enumerate(weighted):
            if index == len(weighted) - 1:
                horas = JORNADA_HORAS - assigned
            else:
                horas = JORNADA_HORAS * pesos / pago
                assigned += horas
            code = _cc_code(name) or name
            key = (day["fecha"], code)
            bucket = buckets.setdefault(
                key,
                {
                    "fecha": day["fecha"],
                    "labor": LABOR,
                    "centro_costo": code,
                    "total_trabajado": 0,
                    "horas_trabajadas": 0.0,
                },
            )
            bucket["total_trabajado"] += pesos
            bucket["horas_trabajadas"] += horas
    return [buckets[key] for key in sorted(buckets)]


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


def _source_tables(source: str) -> dict:
    """Table names and the campo predicate for one harvest app."""
    if source == "zuniga":
        return {
            "escaneo": "appsheet.cosecha_zuniga_escaneo",
            "salidas": "appsheet.cosecha_zuniga_salidas_trabajador",
            "contratistas": "appsheet.cosecha_zuniga_contratistas",
            "cuarteles": "appsheet.cosecha_zuniga_cuarteles",
            "campo_sql": "",
            "salida_sql": "",
            "cuartel_sql": "",
            "tarjas_campo": _TARJAS_CAMPO["zuniga"],
        }
    campo = _APP_CAMPO[source]
    return {
        "escaneo": "appsheet.cosecha_app_escaneo",
        "salidas": "appsheet.cosecha_app_salidas_trabajador",
        "contratistas": "appsheet.cosecha_app_contratistas",
        "cuarteles": "appsheet.cosecha_app_cuarteles",
        "campo_sql": f" AND e.id_campo = '{campo}'",
        "salida_sql": " AND s.id_campo = e.id_campo",
        "cuartel_sql": " AND cu.id_campo = e.id_campo",
        "tarjas_campo": _TARJAS_CAMPO[source],
    }


def _intranet_names(cur) -> list[str]:
    cur.execute(
        """
        SELECT nombre
        FROM intranet.contratistas
        WHERE nombre IS NOT NULL AND btrim(nombre) <> ''
        """
    )
    return [row[0] for row in cur.fetchall()]


def _label_as_legal(label: str, catalog: list[str]) -> str:
    """Geraldina is the app label. The bar shows the one legal name that contains it."""
    folded = fold(label)
    if not folded:
        return label
    longer = []
    same = []
    for legal in catalog:
        other = fold(legal)
        if not other:
            continue
        if other == folded:
            same.append(legal)
            continue
        short, long = (folded, other) if len(folded) <= len(other) else (other, folded)
        if len(short) >= 4 and f" {short} " in f" {long} ":
            longer.append(legal)
    if len(longer) == 1:
        return longer[0]
    if len(same) == 1:
        return same[0]
    return label


def contratistas_en_periodo(cur, fecha_inicio, fecha_termino, empresa=None) -> list[str]:
    """Names the tarjas bar can select. Same label payable() filters on.

    A crew that only scanned capachos has no tarjas_pagos row, so the bar
    would hide them. The intranet link wins. Without it, a short app label
    still becomes the one legal name that contains it.
    """
    predios = predios_for_empresa(empresa)
    if not predios:
        return []
    names: list[str] = []
    seen: set[str] = set()
    catalog = _intranet_names(cur)
    for source in predios:
        tables = _source_tables(source)
        cur.execute(
            f"""
            SELECT DISTINCT nombre
            FROM (
              SELECT COALESCE(
                NULLIF(btrim(m.nombre), ''),
                NULLIF(btrim(c.contratistas), ''),
                NULLIF(btrim(e.contratista), '')
              ) AS nombre
              FROM {tables["escaneo"]} e
              LEFT JOIN {tables["contratistas"]} c
                ON c.id_contratista = e.id_contratista
              LEFT JOIN intranet.contratistas m
                ON m.id_intranet = c.id_intranet_contratistas
              WHERE COALESCE(e.fecha, e.fecha_y_hora::date) BETWEEN %s AND %s
              {tables["campo_sql"]}
            ) names
            WHERE nombre IS NOT NULL AND length(btrim(nombre)) >= 3
            ORDER BY nombre
            """,
            (fecha_inicio, fecha_termino),
        )
        for (name,) in cur.fetchall():
            legal = _label_as_legal(name, catalog)
            if legal not in seen:
                seen.add(legal)
                names.append(legal)
    return names


def _contratista_sql() -> str:
    """Match the bar's legal name or the short name stored on the harvest app."""
    folded_name = (
        "translate(upper(btrim(COALESCE("
        "NULLIF(btrim(c.contratistas), ''), NULLIF(btrim(e.contratista), '')"
        "))), %s, %s)"
    )
    return f"""
      AND (
        COALESCE(
          NULLIF(btrim(m.nombre), ''),
          NULLIF(btrim(c.contratistas), ''),
          NULLIF(btrim(e.contratista), '')
        ) = %s
        OR lower(btrim(COALESCE(m.nombre_corto, ''))) = lower(btrim(%s))
        OR (
          length(btrim(COALESCE(c.contratistas, e.contratista, ''))) >= 3
          AND (
            position({folded_name} IN %s) > 0
            OR position(%s IN {folded_name}) > 0
          )
        )
      )
    """


def _contratista_params(contratista: str) -> list:
    return [
        contratista,
        contratista,
        _FOLD_FROM,
        _FOLD_TO,
        fold(contratista),
        fold(contratista),
        _FOLD_FROM,
        _FOLD_TO,
    ]


def _scan_select(source: str, fecha_inicio, fecha_termino, contratista) -> tuple[str, list]:
    """One scan per row, with the bin id. Manual loads without an id do not count as a bin."""
    tables = _source_tables(source)
    sql = f"""
        SELECT
          COALESCE(e.fecha, e.fecha_y_hora::date) AS fecha,
          NULLIF(btrim(COALESCE(
            NULLIF(e.id_bins, ''),
            CASE
              WHEN lower(btrim(COALESCE(e.bins, ''))) = 'manual' THEN NULL
              ELSE e.bins
            END
          )), '') AS bin_id
        FROM {tables["escaneo"]} e
        LEFT JOIN {tables["contratistas"]} c
          ON c.id_contratista = e.id_contratista
        LEFT JOIN intranet.contratistas m
          ON m.id_intranet = c.id_intranet_contratistas
        WHERE COALESCE(e.fecha, e.fecha_y_hora::date) BETWEEN %s AND %s
        {tables["campo_sql"]}
    """
    params: list = [fecha_inicio, fecha_termino]
    if contratista:
        sql += _contratista_sql()
        params.extend(_contratista_params(contratista))
    return sql, params


def calendar_counts(
    cur,
    grid_start,
    grid_end,
    month_start,
    month_end,
    contratista=None,
    empresa=None,
) -> dict:
    """Capachos and distinct bins per day. Bins are identifiers, never a sum.

    Day counts cover the visible grid. The month totals cover only that month,
    so a bin used on two days counts once in the month.
    """
    empty = {"days": {}, "capachos": 0, "bins": 0}
    predios = predios_for_empresa(empresa)
    if not predios:
        return empty

    def scans(inicio, termino) -> tuple[str, list]:
        parts = []
        params: list = []
        for source in predios:
            sql, source_params = _scan_select(source, inicio, termino, contratista)
            parts.append(sql)
            params.extend(source_params)
        body = " UNION ALL ".join(parts)
        return body, params

    grid_sql, grid_params = scans(grid_start, grid_end)
    cur.execute(
        f"""
        SELECT fecha::text,
               COUNT(*)::int AS capachos,
               COUNT(DISTINCT bin_id) FILTER (WHERE bin_id IS NOT NULL)::int AS bins
        FROM ({grid_sql}) scans
        GROUP BY fecha
        """,
        grid_params,
    )
    days = {
        fecha: {"capachos": int(capachos or 0), "bins": int(bins or 0)}
        for fecha, capachos, bins in cur.fetchall()
        if fecha
    }
    month_sql, month_params = scans(month_start, month_end)
    cur.execute(
        f"""
        SELECT COUNT(*)::int,
               COUNT(DISTINCT bin_id) FILTER (WHERE bin_id IS NOT NULL)::int
        FROM ({month_sql}) scans
        """,
        month_params,
    )
    capachos, bins = cur.fetchone()
    return {
        "days": days,
        "capachos": int(capachos or 0),
        "bins": int(bins or 0),
    }


def payable(cur, fecha_inicio, fecha_termino, contratista=None, empresa=None) -> dict:
    """Harvest amount for a tarjas filter.

    Empresa limits the predio. Empty reads Zúñiga and cosecha_app (Isla de
    Maipo, Talagante). Contratista matches the tarjas legal name through
    the intranet link, or the short name stored on the harvest contractor.
    """
    predios = predios_for_empresa(empresa)
    if not predios:
        return _empty()
    parts = [
        _payable_source(cur, fecha_inicio, fecha_termino, contratista, source)
        for source in predios
    ]
    return _merge_payables(parts)


def _payable_source(cur, fecha_inicio, fecha_termino, contratista, source: str) -> dict:
    tables = _source_tables(source)
    sql = f"""
        SELECT
          COALESCE(e.fecha, e.fecha_y_hora::date) AS fecha,
          COALESCE(NULLIF(btrim(e.trabajador), ''), '(sin nombre)') AS trabajador,
          COALESCE(
            NULLIF(btrim(m.nombre), ''),
            NULLIF(btrim(c.contratistas), ''),
            NULLIF(btrim(e.contratista), '')
          ) AS contratista,
          NULLIF(btrim(m.nombre_corto), '') AS nombre_corto,
          COALESCE(
            NULLIF(btrim(cu.nombre_cuartel), ''),
            NULLIF(btrim(e.cuartel), ''),
            'Sin cuartel'
          ) AS cuartel,
          NULLIF(btrim(cu.cultivo), '') AS cultivo,
          e.precio_trato_aplicado AS precio,
          COALESCE(s.accion_piso, e.piso_aplicado) AS piso
        FROM {tables["escaneo"]} e
        LEFT JOIN {tables["salidas"]} s
          ON s.fecha = COALESCE(e.fecha, e.fecha_y_hora::date)
         AND s.id_qr = e.id_qr
         {tables["salida_sql"]}
        LEFT JOIN {tables["contratistas"]} c
          ON c.id_contratista = e.id_contratista
        LEFT JOIN intranet.contratistas m
          ON m.id_intranet = c.id_intranet_contratistas
        LEFT JOIN {tables["cuarteles"]} cu
          ON cu.id_cuartel = e.cuartel
         {tables["cuartel_sql"]}
        WHERE COALESCE(e.fecha, e.fecha_y_hora::date) BETWEEN %s AND %s
        {tables["campo_sql"]}
    """
    params: list = [fecha_inicio, fecha_termino]
    if contratista:
        # The tarjas bar uses the legal name. The app may only store the
        # short one (Herbi inside HERBI ML SPA) and have no intranet link.
        sql += _contratista_sql()
        params.extend(_contratista_params(contratista))
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
        # A day with only the floor is still cosecha a trato. The label
        # identifies it; the amount is the floor, unchanged.
        solo_piso = day["trato"] == 0 and day["piso"] > 0
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
                "al_dia": False,
                "solo_piso": solo_piso,
                "tipo_pago": TIPO_TRATO,
                "labor": LABOR,
            }
        )
    personas_dias.sort(key=lambda row: (row["trabajador"], row["fecha"]))

    lines = _document_lines(days)
    celdas = jornada_cells(days)
    codes = [line["cc"] for line in lines if line.get("cc")]
    codes.extend(cell["centro_costo"] for cell in celdas if cell.get("centro_costo"))
    if codes:
        cur.execute(
            """
            SELECT id_cc::text, cultivo, valor_odoo
            FROM appsheet.tarjas_cc
            WHERE id_campo = %s AND id_cc::text = ANY(%s)
            """,
            (tables["tarjas_campo"], codes),
        )
        names = {code: (cultivo, valor) for code, cultivo, valor in cur.fetchall()}
        for line in lines:
            cultivo, valor = names.get(line.get("cc"), ("", None))
            line["cultivo"] = cultivo or ""
            line["valor_odoo"] = valor
        for cell in celdas:
            cultivo, valor = names.get(cell.get("centro_costo"), ("", None))
            cell["cultivo"] = cultivo or ""
            cell["valor_odoo"] = valor
    cuarteles_pago = _pay_by_cuartel(days)
    total = sum(row["a_pagar"] for row in personas_dias)
    jornadas = len(personas_dias)
    return {
        "es_cosecha": True,
        "total": total,
        "trato": sum(row["trato"] for row in personas_dias),
        "piso": sum(row["piso"] for row in personas_dias),
        "pago_trato": total,
        "pago_al_dia": 0,
        "jornadas_trato": jornadas,
        "jornadas_al_dia": 0,
        "capachos": sum(row["capachos"] for row in personas_dias),
        "jornadas": jornadas,
        "personas": len({row["trabajador"] for row in personas_dias}),
        "promedio_diario": round(total / jornadas) if jornadas else None,
        "lines": lines,
        "personas_dias": personas_dias,
        "cuarteles_pago": cuarteles_pago,
        "celdas": celdas,
    }


def _merge_payables(parts: list[dict]) -> dict:
    filled = [part for part in parts if part["personas_dias"]]
    if not filled:
        return _empty()
    if len(filled) == 1:
        return filled[0]
    personas_dias = []
    lines = []
    celdas = []
    cuarteles_pago = []
    for part in filled:
        personas_dias.extend(part["personas_dias"])
        lines.extend(part["lines"])
        celdas.extend(part["celdas"])
        cuarteles_pago.extend(part["cuarteles_pago"])
    personas_dias.sort(key=lambda row: (row["trabajador"], row["fecha"]))
    total = sum(row["a_pagar"] for row in personas_dias)
    jornadas = len(personas_dias)
    return {
        "es_cosecha": True,
        "total": total,
        "trato": sum(row["trato"] for row in personas_dias),
        "piso": sum(row["piso"] for row in personas_dias),
        "pago_trato": total,
        "pago_al_dia": 0,
        "jornadas_trato": jornadas,
        "jornadas_al_dia": 0,
        "capachos": sum(row["capachos"] for row in personas_dias),
        "jornadas": jornadas,
        "personas": len({row["trabajador"] for row in personas_dias}),
        "promedio_diario": round(total / jornadas) if jornadas else None,
        "lines": lines,
        "personas_dias": personas_dias,
        "cuarteles_pago": cuarteles_pago,
        "celdas": celdas,
    }
