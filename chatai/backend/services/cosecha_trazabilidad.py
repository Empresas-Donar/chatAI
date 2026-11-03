"""Worker trace for Zúñiga harvest.

Each scan keeps its own copy of the worker. Deleting the QR credential
does not remove those rows. This search reads both and says when they diverge.
"""

from __future__ import annotations

import re
from collections import defaultdict

from services.cosecha_rendimiento import (
    _FOLD_FROM,
    _FOLD_TO,
    _money,
    amount_due,
    fold,
    predios_for_empresa,
)

_MIN_CHARS = 3
_FOLD = f"translate(upper(coalesce({{col}}, '')), '{_FOLD_FROM}', '{_FOLD_TO}')"
_RUT = "regexp_replace(upper(coalesce({col}, '')), '[^0-9K]', '', 'g')"


class SearchTooShort(ValueError):
    """The query needs at least three letters or a RUT fragment."""


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _rut_key(value: str | None) -> str:
    return re.sub(r"[^0-9K]", "", fold(value))


def _crew(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".00"):
        return text[:-3]
    if text.endswith(".0"):
        return text[:-2]
    return text


def _iso(value) -> str:
    if value is None:
        return ""
    return str(value)[:10]


def _hora(value) -> str:
    if value is None or not hasattr(value, "strftime"):
        return ""
    return value.strftime("%H:%M")


def _tokens(query: str) -> list[str]:
    return [part for part in fold(query).split() if len(part) >= 2]


def _match_sql(name_col: str, rut_col: str, text: str) -> tuple[str, list]:
    tokens = _tokens(text)
    rut = _rut_key(text)
    if len(fold(text)) < _MIN_CHARS and len(rut) < _MIN_CHARS:
        raise SearchTooShort(text)
    if not tokens and len(rut) < _MIN_CHARS:
        raise SearchTooShort(text)
    clauses = []
    params: list = []
    folded = _FOLD.format(col=name_col)
    if tokens:
        clauses.append("(" + " AND ".join(f"{folded} LIKE %s ESCAPE '\\'" for _ in tokens) + ")")
        params.extend(_like(token) for token in tokens)
    if len(rut) >= _MIN_CHARS:
        clauses.append(_RUT.format(col=rut_col) + " LIKE %s ESCAPE '\\'")
        params.append(_like(rut))
    return " OR ".join(clauses), params


def _contractor_expr() -> str:
    col = "COALESCE(NULLIF(btrim(c.contratistas), ''), NULLIF(btrim(e.contratista), ''))"
    return _FOLD.format(col=col)


def _scan_scope(desde: str | None, hasta: str | None, contratista: str | None) -> tuple[str, list]:
    """Date and contractor limits shared by the picker and the person detail."""
    clauses = []
    params: list = []
    if desde:
        clauses.append("COALESCE(e.fecha::date, e.fecha_y_hora::date) >= %s::date")
        params.append(desde)
    if hasta:
        clauses.append("COALESCE(e.fecha::date, e.fecha_y_hora::date) <= %s::date")
        params.append(hasta)
    folded = fold(contratista)
    if folded:
        expr = _contractor_expr()
        clauses.append(
            f"({expr} = %s OR position({expr} in %s) > 0 OR position(%s in {expr}) > 0)"
        )
        params.extend([folded, folded, folded])
    return (" AND ".join(clauses) if clauses else "TRUE"), params


def list_workers(cur, empresa=None, contratista=None, desde=None, hasta=None) -> dict:
    """One row per person who worked inside the global filters."""
    if not predios_for_empresa(empresa):
        return {"trabajadores": []}
    scope_sql, scope_params = _scan_scope(desde, hasta, contratista)
    cur.execute(
        f"""
        SELECT
          CASE
            WHEN {_RUT.format(col='e.rut_trabajador')} <> ''
              THEN {_RUT.format(col='e.rut_trabajador')}
            ELSE {_FOLD.format(col='e.trabajador')}
          END AS person_key,
          (array_agg(e.trabajador ORDER BY e.fecha_y_hora DESC NULLS LAST))[1] AS nombre,
          (array_agg(e.rut_trabajador ORDER BY e.fecha_y_hora DESC NULLS LAST))[1] AS rut,
          (array_agg(
            COALESCE(NULLIF(btrim(c.contratistas), ''), NULLIF(btrim(e.contratista), ''))
            ORDER BY e.fecha_y_hora DESC NULLS LAST
          ))[1] AS contratista,
          (array_agg(e.cuadrilla::text ORDER BY e.fecha_y_hora DESC NULLS LAST))[1] AS cuadrilla,
          count(*)::int AS capachos,
          count(DISTINCT COALESCE(e.fecha::date, e.fecha_y_hora::date))::int AS dias_trabajados
        FROM appsheet.cosecha_zuniga_escaneo e
        LEFT JOIN appsheet.cosecha_zuniga_contratistas c
          ON c.id_contratista = e.id_contratista
        WHERE (NULLIF(btrim(e.trabajador), '') IS NOT NULL
           OR NULLIF(btrim(e.rut_trabajador), '') IS NOT NULL)
          AND {scope_sql}
        GROUP BY 1
        """,
        scope_params,
    )
    people = {}
    for key, nombre, rut, contratista, cuadrilla, capachos, dias_trabajados in cur.fetchall():
        if not key:
            continue
        people[key] = {
            "nombre": nombre or "",
            "rut": rut or "",
            "contratista": contratista or "",
            "cuadrilla": _crew(cuadrilla),
            "capachos": capachos,
            "dias_trabajados": dias_trabajados,
        }
    limited = bool(desde or hasta or contratista)
    if not limited:
        cur.execute(
            f"""
            SELECT
              CASE
                WHEN {_RUT.format(col='q.rut')} <> '' THEN {_RUT.format(col='q.rut')}
                ELSE {_FOLD.format(col='q.trabajador')}
              END AS person_key,
              q.trabajador,
              q.rut,
              COALESCE(NULLIF(btrim(c.contratistas), ''), '') AS contratista,
              q.cuadrilla::text
            FROM appsheet.cosecha_zuniga_qr q
            LEFT JOIN appsheet.cosecha_zuniga_contratistas c
              ON c.id_contratista = q.id_contratista
            WHERE NULLIF(btrim(q.trabajador), '') IS NOT NULL
               OR NULLIF(btrim(q.rut), '') IS NOT NULL
            """
        )
    for key, nombre, rut, contratista, cuadrilla in ([] if limited else cur.fetchall()):
        if not key or key in people:
            continue
        people[key] = {
            "nombre": nombre or "",
            "rut": rut or "",
            "contratista": contratista or "",
            "cuadrilla": _crew(cuadrilla),
            "capachos": 0,
            "dias_trabajados": 0,
        }
    trabajadores = sorted(people.values(), key=lambda row: (fold(row["nombre"]), row["rut"]))
    return {"trabajadores": trabajadores}


def search_workers(cur, query: str, empresa=None, contratista=None, desde=None, hasta=None) -> dict:
    """People matching a name or RUT, limited to the global filters."""
    text = (query or "").strip()
    scan_where, scan_params = _match_sql("e.trabajador", "e.rut_trabajador", text)
    if not predios_for_empresa(empresa):
        return {"q": text, "predio": "Zúñiga", "personas": []}
    scope_sql, scope_params = _scan_scope(desde, hasta, contratista)
    limited = bool(desde or hasta or contratista)

    cur.execute(_scan_sql(f"({scan_where}) AND ({scope_sql})"), scan_params + scope_params)
    matched_scans = cur.fetchall()
    matched_qr = []
    if not limited:
        qr_where, qr_params = _match_sql("q.trabajador", "q.rut", text)
        cur.execute(_qr_sql(qr_where), qr_params)
        matched_qr = cur.fetchall()

    ruts, names = _keys(matched_scans, matched_qr)
    scans, fichas = (matched_scans, matched_qr)
    if ruts or names:
        scans, fichas = _expand(cur, ruts, names, scope_sql, scope_params)

    codes = _unique(row[11] for row in scans)
    by_code = _credentials_by_code(cur, codes) if codes else {}
    people = _people(scans, fichas, by_code)
    if limited:
        people = [person for person in people if person["capachos"]]
    return {"q": text, "predio": "Zúñiga", "personas": people}


def _scan_sql(where: str) -> str:
    return f"""
        SELECT
          COALESCE(e.fecha, e.fecha_y_hora::date) AS fecha,
          e.fecha_y_hora,
          e.trabajador,
          e.rut_trabajador,
          e.cuadrilla,
          COALESCE(NULLIF(btrim(c.contratistas), ''), NULLIF(btrim(e.contratista), '')) AS contratista,
          e.bins,
          e.cuartel,
          NULLIF(btrim(cu.nombre_cuartel), '') AS nombre_cuartel,
          e.precio_trato_aplicado,
          COALESCE(s.accion_piso, e.piso_aplicado) AS piso_aplicado,
          e.codigo_qr,
          e.id_qr
        FROM appsheet.cosecha_zuniga_escaneo e
        LEFT JOIN appsheet.cosecha_zuniga_salidas_trabajador s
          ON s.fecha = COALESCE(e.fecha, e.fecha_y_hora::date)
         AND s.id_qr = e.id_qr
        LEFT JOIN appsheet.cosecha_zuniga_contratistas c
          ON c.id_contratista = e.id_contratista
        LEFT JOIN appsheet.cosecha_zuniga_cuarteles cu
          ON cu.id_cuartel = e.cuartel
        WHERE {where}
        ORDER BY e.fecha_y_hora
    """


def _qr_sql(where: str) -> str:
    return f"""
        SELECT
          q.id_qr,
          q.qr_trabajador,
          q.trabajador,
          q.rut,
          q.cuadrilla,
          COALESCE(NULLIF(btrim(c.contratistas), ''), '') AS contratista
        FROM appsheet.cosecha_zuniga_qr q
        LEFT JOIN appsheet.cosecha_zuniga_contratistas c
          ON c.id_contratista = q.id_contratista
        WHERE {where}
    """


def _keys(scans, fichas) -> tuple[set[str], set[str]]:
    ruts: set[str] = set()
    names: set[str] = set()
    for row in scans:
        rut = _rut_key(row[3])
        if rut:
            ruts.add(rut)
        elif fold(row[2]):
            names.add(fold(row[2]))
    for row in fichas:
        rut = _rut_key(row[3])
        if rut:
            ruts.add(rut)
        elif fold(row[2]):
            names.add(fold(row[2]))
    return ruts, names


def _expand(cur, ruts: set[str], names: set[str], scope_sql="TRUE", scope_params=None) -> tuple[list, list]:
    """Every scan and credential of the matched people, including other name spellings."""
    scan_filter = []
    scan_params: list = []
    qr_filter = []
    qr_params: list = []
    if ruts:
        scan_filter.append(_RUT.format(col="e.rut_trabajador") + " = ANY(%s)")
        scan_params.append(list(ruts))
        qr_filter.append(_RUT.format(col="q.rut") + " = ANY(%s)")
        qr_params.append(list(ruts))
    if names:
        folded = _FOLD.format(col="e.trabajador")
        scan_filter.append(
            f"({_RUT.format(col='e.rut_trabajador')} = '' AND {folded} = ANY(%s))"
        )
        scan_params.append(list(names))
        qr_folded = _FOLD.format(col="q.trabajador")
        qr_filter.append(f"({_RUT.format(col='q.rut')} = '' AND {qr_folded} = ANY(%s))")
        qr_params.append(list(names))

    scope_params = list(scope_params or [])
    cur.execute(
        _scan_sql(f"({' OR '.join(scan_filter)}) AND ({scope_sql})"),
        scan_params + scope_params,
    )
    scans = cur.fetchall()
    cur.execute(_qr_sql(" OR ".join(qr_filter)), qr_params)
    return scans, cur.fetchall()


def _credentials_by_code(cur, codes: list[str]) -> dict:
    cur.execute(_qr_sql("q.qr_trabajador = ANY(%s)"), (codes,))
    found = {}
    for row in cur.fetchall():
        found[row[1]] = row
    return found


def _identity(rut: str, nombre: str) -> str:
    return f"rut:{rut}" if rut else f"nombre:{nombre}"


def _people(scans, fichas, by_code: dict) -> list[dict]:
    grouped_scans = defaultdict(list)
    grouped_qr = defaultdict(list)
    for row in scans:
        grouped_scans[_identity(_rut_key(row[3]), fold(row[2]))].append(row)
    for row in fichas:
        grouped_qr[_identity(_rut_key(row[3]), fold(row[2]))].append(row)

    people = []
    for key in set(grouped_scans) | set(grouped_qr):
        people.append(_person(grouped_scans.get(key, []), grouped_qr.get(key, []), by_code))
    people.sort(key=lambda person: (-person["capachos"], person["nombre"]))
    return people


def _unique(values) -> list[str]:
    seen = []
    for value in values:
        text = (value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _ficha(card) -> dict:
    return {
        "codigo_qr": card[1] or "",
        "trabajador": card[2] or "",
        "rut": card[3] or "",
        "cuadrilla": _crew(card[4]),
        "contratista": card[5] or "",
    }


def _person(rows, cards, by_code: dict) -> dict:
    nombres = _unique(row[2] for row in rows) or _unique(card[2] for card in cards)
    ruts = _unique(row[3] for row in rows) or _unique(card[3] for card in cards)
    person_ruts = {_rut_key(rut) for rut in ruts if _rut_key(rut)}
    fichas = [_ficha(card) for card in cards]
    codigos = _unique(row[11] for row in rows)

    ausentes = []
    reasignadas = []
    for code in codigos:
        current = by_code.get(code)
        if current is None:
            ausentes.append(code)
            continue
        if person_ruts and _rut_key(current[3]) not in person_ruts:
            reasignadas.append(_ficha(current))

    propias = [
        ficha
        for ficha in fichas
        if (_rut_key(ficha["rut"]) and _rut_key(ficha["rut"]) in person_ruts)
        or (not person_ruts and fold(ficha["trabajador"]) in {fold(nombre) for nombre in nombres})
    ]
    vigente = bool(propias)

    escaneos = [_scan(row) for row in rows]
    dias = _days(rows)
    qrs = _qrs(rows, ausentes, reasignadas)
    por_cuadrilla = _crews(rows)
    alertas = _alerts(nombres, ausentes, reasignadas, fichas, rows)
    return {
        "nombre": nombres[-1] if nombres else "",
        "nombres": nombres,
        "rut": ruts[0] if ruts else "",
        "contratistas": contratistas_de(rows, fichas),
        "cuadrillas": _unique(_crew(row[4]) for row in rows) or _unique(f["cuadrilla"] for f in fichas),
        "cuadrillas_trabajadas": len(por_cuadrilla),
        "dias_trabajados": len(dias),
        "qrs_usados": len(qrs),
        "qrs": qrs,
        "por_cuadrilla": por_cuadrilla,
        "capachos": len(escaneos),
        "desde": escaneos[0]["fecha"] if escaneos else "",
        "hasta": escaneos[-1]["fecha"] if escaneos else "",
        "credencial_vigente": vigente,
        "fichas": fichas,
        "codigos_ausentes": ausentes,
        "alertas": alertas,
        "dias": dias,
        "escaneos": escaneos,
        "trato": sum(day["trato"] for day in dias),
        "piso": sum(day["piso"] for day in dias),
        "a_pagar": sum(day["a_pagar"] for day in dias),
    }


def _qrs(rows, ausentes, reasignadas) -> list[dict]:
    buckets = defaultdict(list)
    for row in rows:
        code = (row[11] or "").strip()
        if code:
            buckets[code].append(row)
    moved = {ficha["codigo_qr"] for ficha in reasignadas}
    items = []
    for code, group in buckets.items():
        if code in ausentes:
            estado = "no está en el catálogo"
        elif code in moved:
            estado = "reasignada"
        else:
            estado = "vigente"
        items.append(
            {
                "codigo_qr": code,
                "capachos": len(group),
                "cuadrillas": _unique(_crew(row[4]) for row in group),
                "desde": _iso(group[0][0]),
                "hasta": _iso(group[-1][0]),
                "estado": estado,
            }
        )
    items.sort(key=lambda item: (item["desde"], item["codigo_qr"]))
    return items


def _crews(rows) -> list[dict]:
    buckets = defaultdict(list)
    for row in rows:
        buckets[_crew(row[4]) or "—"].append(row)
    items = []
    for crew, group in buckets.items():
        items.append(
            {
                "cuadrilla": crew,
                "contratistas": _unique(row[5] for row in group),
                "capachos": len(group),
                "qrs": len(_unique(row[11] for row in group)),
                "desde": _iso(group[0][0]),
                "hasta": _iso(group[-1][0]),
            }
        )
    items.sort(key=lambda item: item["cuadrilla"])
    return items


def contratistas_de(rows, fichas) -> list[str]:
    found = _unique(row[5] for row in rows)
    if found:
        return found
    return _unique(ficha["contratista"] for ficha in fichas)


def _scan(row) -> dict:
    lugar = f"{row[7] or ''} {row[8] or ''}".strip()
    return {
        "fecha": _iso(row[0]),
        "hora": _hora(row[1]),
        "contratista": row[5] or "",
        "cuadrilla": _crew(row[4]),
        "bins": "" if row[6] is None else str(row[6]),
        "cuartel": lugar,
        "precio": _money(row[9]),
        "codigo_qr": row[11] or "",
    }


def _days(rows) -> list[dict]:
    buckets = defaultdict(list)
    for row in rows:
        buckets[_iso(row[0])].append(row)
    days = []
    for fecha in sorted(buckets):
        group = buckets[fecha]
        trato = sum(_money(row[9]) for row in group)
        piso = max((_money(row[10]) for row in group), default=0)
        days.append(
            {
                "fecha": fecha,
                "capachos": len(group),
                "desde": _hora(group[0][1]),
                "hasta": _hora(group[-1][1]),
                "contratistas": _unique(row[5] for row in group),
                "cuadrillas": _unique(_crew(row[4]) for row in group),
                "cuarteles": _unique(f"{row[7] or ''} {row[8] or ''}".strip() for row in group),
                "trato": trato,
                "piso": piso,
                "a_pagar": amount_due(trato, piso),
            }
        )
    return days


def _alerts(nombres, ausentes, reasignadas, fichas, rows) -> list[str]:
    notes = []
    if len(nombres) > 1:
        notes.append("El nombre figura como " + " y ".join(nombres) + ".")
    for code in ausentes:
        notes.append(
            f"La credencial {code} no está en el catálogo. Los capachos siguen en el escaneo."
        )
    for ficha in reasignadas:
        quien = ficha["trabajador"] or "otro trabajador"
        donde = ficha["contratista"] or "sin contratista"
        notes.append(f"La credencial {ficha['codigo_qr']} quedó a nombre de {quien} ({donde}).")
    if rows and not fichas and not ausentes and not reasignadas:
        notes.append("No tiene credencial en el catálogo. Los capachos siguen en el escaneo.")
    if fichas and not rows:
        notes.append("Está en el catálogo de QR y no tiene capachos.")
    cero = sum(1 for row in rows if _money(row[9]) == 0)
    if cero:
        notes.append(f"{cero} capachos quedaron a precio $0.")
    return notes
