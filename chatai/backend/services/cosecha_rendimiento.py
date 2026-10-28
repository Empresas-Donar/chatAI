"""Harvest yield for the operational detail report.

Amounts are the scanned piece rate and the daily floor copied onto each
capacho. They do not pass through tarjas_empresa (no × 1.45 / × 1.50).
"""

from __future__ import annotations

import datetime
import decimal
import unicodedata
from typing import Any

_FOLD_FROM = "ÁÉÍÓÚÜÑÀÈÌÒÙ"
_FOLD_TO = "AEIOUUNAEIOU"

_SOURCES = ("zuniga",)
_EMPRESA_LABEL = {
    "zuniga": "ZUÑIGA",
}


def fold(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.upper().split())


def predios_for_empresa(empresa: str | None) -> list[str]:
    """Map the shared Empresa filter onto the harvest app.

    The detail report reads only cosecha_zuniga. Empty or Zúñiga returns
    that predio. Isla de Maipo, Talagante and KONTROLAG return none.
    """
    folded = fold(empresa)
    if not folded or "ZUNIGA" in folded:
        return ["zuniga"]
    return []


def amount_due(trato, piso) -> int:
    """Capacho pay plus the daily floor. The floor is added once; it does not replace the piece rate."""
    return _money(trato) + _money(piso)


def _money(value) -> int:
    if value is None:
        return 0
    return int(
        decimal.Decimal(str(value)).quantize(
            decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP
        )
    )


def _per_person(capachos: int, personas: int):
    if not personas:
        return None
    return round(capachos / personas, 1)


def _scan_sql(source: str) -> str:
    if source == "zuniga":
        return """
            SELECT
              'Zúñiga'::text AS predio,
              COALESCE(e."fecha", e."fecha_y_hora"::date) AS fecha,
              COALESCE(c."contratistas", e."contratista") AS contratista,
              trunc(e."cuadrilla")::int AS cuadrilla,
              COALESCE(cu."nombre_cuartel", e."cuartel") AS cuartel,
              e."cuartel" AS cuartel_id,
              cu."cultivo" AS cultivo,
              COALESCE(e."variedad", cu."variedad") AS variedad,
              e."trabajador" AS trabajador,
              e."precio_trato_aplicado" AS precio,
              e."piso_aplicado" AS piso,
              COALESCE(e."id_bins", e."bins") AS bin_key
            FROM appsheet.cosecha_zuniga_escaneo e
            LEFT JOIN appsheet.cosecha_zuniga_contratistas c
              ON c."id_contratista" = e."id_contratista"
            LEFT JOIN appsheet.cosecha_zuniga_cuarteles cu
              ON cu."id_cuartel" = e."cuartel"
        """
    raise ValueError(source)


def _scans_cte(predios: list[str]) -> str:
    branches = " UNION ALL ".join(_scan_sql(source) for source in predios)
    return f"""
        WITH scans AS (
          SELECT * FROM (
            {branches}
          ) raw
          WHERE raw.fecha IS NOT NULL
            AND (%(desde)s IS NULL OR raw.fecha >= %(desde)s)
            AND (%(hasta)s IS NULL OR raw.fecha <= %(hasta)s)
            AND (
              %(contratista)s IS NULL
              OR (
                length(trim(coalesce(raw.contratista, ''))) >= 3
                AND (
                  translate(upper(raw.contratista), '{_FOLD_FROM}', '{_FOLD_TO}')
                    = %(contratista)s
                  OR position(
                    translate(upper(raw.contratista), '{_FOLD_FROM}', '{_FOLD_TO}')
                    IN %(contratista)s
                  ) > 0
                  OR position(
                    %(contratista)s
                    IN translate(upper(raw.contratista), '{_FOLD_FROM}', '{_FOLD_TO}')
                  ) > 0
                )
              )
            )
            AND (
              %(cuartel)s IS NULL
              OR raw.cuartel = %(cuartel)s
              OR raw.cuartel_id = %(cuartel)s
            )
            AND (%(cuadrilla)s IS NULL OR raw.cuadrilla = %(cuadrilla)s)
            AND (%(cultivo)s IS NULL OR raw.cultivo = %(cultivo)s)
        )
    """


def _params(
    fecha_inicio: str | None,
    fecha_termino: str | None,
    contratista: str | None,
    cuartel: str | None,
    cuadrilla: int | None,
    cultivo: str | None,
) -> dict[str, Any]:
    return {
        "desde": fecha_inicio or None,
        "hasta": fecha_termino or None,
        "contratista": fold(contratista) or None,
        "cuartel": (cuartel or "").strip() or None,
        "cuadrilla": cuadrilla,
        "cultivo": (cultivo or "").strip() or None,
    }


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)[:10]


def _row_out(row: dict) -> dict:
    trato = _money(row["trato"])
    piso = _money(row["piso"])
    return {
        "fecha": _iso(row["fecha"]),
        "predio": row["predio"],
        "contratista": row["contratista"],
        "cuadrilla": row["cuadrilla"],
        "cuartel": row["cuartel"],
        "cultivo": row["cultivo"],
        "variedad": row["variedad"],
        "trabajador": row["trabajador"],
        "capachos": int(row["capachos"] or 0),
        "precio": None if row["precio"] is None else _money(row["precio"]),
        "trato": trato,
        "piso": piso,
        "a_pagar": amount_due(trato, piso),
    }


def _empty(hint: dict | None = None) -> dict:
    return {
        "rows": [],
        "resumen": [],
        "totales": {
            "capachos": 0,
            "trabajadores": 0,
            "jornadas": 0,
            "capachos_persona": None,
            "trato": 0,
            "a_pagar": 0,
        },
        "hint": hint,
    }


def query_detalle(
    cur,
    fecha_inicio: str,
    fecha_termino: str,
    empresa: str | None = None,
    contratista: str | None = None,
    cuartel: str | None = None,
    cuadrilla: int | None = None,
    cultivo: str | None = None,
) -> dict:
    predios = predios_for_empresa(empresa)
    if not predios:
        return _empty()

    params = _params(
        fecha_inicio, fecha_termino, contratista, cuartel, cuadrilla, cultivo
    )
    cte = _scans_cte(predios)
    cur.execute(
        cte
        + """
        SELECT
          fecha, predio, contratista, cuadrilla, cuartel, cultivo, variedad,
          trabajador,
          count(*)::int AS capachos,
          CASE
            WHEN count(DISTINCT precio) = 1 THEN min(precio)
            ELSE NULL
          END AS precio,
          COALESCE(sum(precio), 0) AS trato,
          COALESCE(max(piso), 0) AS piso
        FROM scans
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
        ORDER BY fecha, cuadrilla NULLS LAST, count(*) DESC, trabajador
        """,
        params,
    )
    cols = [d[0] for d in cur.description]
    rows = [_row_out(dict(zip(cols, rec))) for rec in cur.fetchall()]

    cur.execute(
        cte
        + """
        SELECT
          fecha, predio, contratista, cuadrilla, cuartel, cultivo, variedad,
          count(DISTINCT bin_key) FILTER (
            WHERE bin_key IS NOT NULL AND btrim(bin_key) <> ''
          )::int AS bins
        FROM scans
        GROUP BY 1, 2, 3, 4, 5, 6, 7
        """,
        params,
    )
    bin_cols = [d[0] for d in cur.description]
    bins_by_key = {}
    for rec in cur.fetchall():
        item = dict(zip(bin_cols, rec))
        bins_by_key[_group_key(item)] = int(item["bins"] or 0)

    if not rows:
        return _empty(_hint(cur, predios, params))

    resumen_map: dict[tuple, dict] = {}
    for row in rows:
        key = _group_key(row)
        bucket = resumen_map.get(key)
        if bucket is None:
            bucket = {
                "fecha": row["fecha"],
                "predio": row["predio"],
                "contratista": row["contratista"],
                "cuadrilla": row["cuadrilla"],
                "cuartel": row["cuartel"],
                "cultivo": row["cultivo"],
                "variedad": row["variedad"],
                "trabajadores": 0,
                "capachos": 0,
                "trato": 0,
                "a_pagar": 0,
                "bins": bins_by_key.get(key, 0),
            }
            resumen_map[key] = bucket
        bucket["trabajadores"] += 1
        bucket["capachos"] += row["capachos"]
        bucket["trato"] += row["trato"]
        bucket["a_pagar"] += row["a_pagar"]

    resumen = list(resumen_map.values())
    resumen.sort(key=lambda r: (r["fecha"] or "", r["cuadrilla"] or 0, r["cuartel"] or ""))
    for item in resumen:
        item["capachos_persona"] = _per_person(item["capachos"], item["trabajadores"])

    trabajadores = len(
        {(r["predio"], r["trabajador"]) for r in rows if r["trabajador"]}
    )
    capachos = sum(r["capachos"] for r in rows)
    return {
        "rows": rows,
        "resumen": resumen,
        "totales": {
            "capachos": capachos,
            "trabajadores": trabajadores,
            "jornadas": len(rows),
            "capachos_persona": _per_person(capachos, len(rows)),
            "trato": sum(r["trato"] for r in rows),
            "a_pagar": sum(r["a_pagar"] for r in rows),
        },
        "hint": None,
    }


def _group_key(row: dict) -> tuple:
    return (
        _iso(row["fecha"]) if not isinstance(row["fecha"], str) else row["fecha"],
        row["predio"],
        row["contratista"],
        row["cuadrilla"],
        row["cuartel"],
        row["cultivo"],
        row["variedad"],
    )


def _hint(cur, predios: list[str], params: dict) -> dict | None:
    open_params = dict(params)
    open_params["desde"] = None
    open_params["hasta"] = None
    cur.execute(
        _scans_cte(predios)
        + """
        SELECT count(*)::int AS capachos, min(fecha) AS desde, max(fecha) AS hasta
        FROM scans
        """,
        open_params,
    )
    capachos, desde, hasta = cur.fetchone()
    if not capachos:
        return None
    return {"capachos": capachos, "desde": _iso(desde), "hasta": _iso(hasta)}


def _scope_predios(empresa: str | None) -> list[str]:
    """Predios for a cosecha filter. An empresa without harvest does not narrow."""
    if not fold(empresa):
        return ["zuniga"]
    return predios_for_empresa(empresa) or ["zuniga"]


def _empresas_con_cosecha(
    cur,
    contratista: str | None,
    fecha_inicio: str | None,
    fecha_termino: str | None,
) -> list[str]:
    """Predios with at least one capacho in the selected period and contractor."""
    found = []
    params = _params(fecha_inicio, fecha_termino, contratista, None, None, None)
    for source in _SOURCES:
        cur.execute(
            _scans_cte([source]) + " SELECT 1 FROM scans LIMIT 1",
            params,
        )
        if cur.fetchone():
            found.append(_EMPRESA_LABEL[source])
    return found


def _contratistas_con_cosecha(
    cur,
    predios: list[str],
    fecha_inicio: str | None,
    fecha_termino: str | None,
) -> list[str]:
    params = _params(fecha_inicio, fecha_termino, None, None, None, None)
    cur.execute(
        _scans_cte(predios)
        + """
        SELECT DISTINCT contratista
        FROM scans
        WHERE contratista IS NOT NULL AND length(btrim(contratista)) >= 3
        ORDER BY 1
        """,
        params,
    )
    return [r[0] for r in cur.fetchall()]


def filter_options(
    cur,
    empresa: str | None = None,
    contratista: str | None = None,
    fecha_inicio: str | None = None,
    fecha_termino: str | None = None,
) -> dict:
    empresas = _empresas_con_cosecha(cur, contratista, fecha_inicio, fecha_termino)
    predios = _scope_predios(empresa)
    contratistas = _contratistas_con_cosecha(cur, predios, fecha_inicio, fecha_termino)
    params = _params(fecha_inicio, fecha_termino, None, None, None, None)
    cte = _scans_cte(predios)
    cur.execute(
        cte
        + """
        SELECT DISTINCT cuartel
        FROM scans
        WHERE cuartel IS NOT NULL AND btrim(cuartel) <> ''
        ORDER BY 1
        """,
        params,
    )
    cuarteles = [r[0] for r in cur.fetchall()]
    cur.execute(
        cte
        + """
        SELECT DISTINCT cuadrilla
        FROM scans
        WHERE cuadrilla IS NOT NULL
        ORDER BY 1
        """,
        params,
    )
    cuadrillas = [int(r[0]) for r in cur.fetchall()]
    cur.execute(
        cte
        + """
        SELECT DISTINCT cultivo
        FROM scans
        WHERE cultivo IS NOT NULL AND btrim(cultivo) <> ''
        ORDER BY 1
        """,
        params,
    )
    cultivos = [r[0] for r in cur.fetchall()]
    return {
        "empresas": empresas,
        "contratistas": contratistas,
        "cuarteles": cuarteles,
        "cuadrillas": cuadrillas,
        "cultivos": cultivos,
    }
