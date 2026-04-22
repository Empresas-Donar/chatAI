"""
controllers/tarjas_controller.py
---------------------------------
HTTP layer for the Tarjas reports (replaces Looker Studio pages).

Routes:
  GET  /tarjas/general                  → General operational overview
  GET  /api/tarjas/general/filters      → Filter options (general)
  GET  /api/tarjas/general              → Aggregated data (labor summary, person ranking, chart)

  GET  /tarjas/detalle                  → Weekly detail page
  GET  /api/tarjas/detalle/filters      → Filter options (detalle)
  GET  /api/tarjas/detalle              → Detail data

  GET  /tarjas/detalle-tractorista       → Weekly tractorista detail (Looker)
  GET  /api/tarjas/detalle-tractorista/filters
  GET  /api/tarjas/detalle-tractorista   → Summary by contractor + detail rows

  GET  /tarjas/contratista              → Contractor/worker pivot page
  GET  /api/tarjas/contratista/filters  → Filter options (contratista)
  GET  /api/tarjas/contratista          → Worker-level data for pivot table

  GET  /tarjas/contratista-tractorista       → Tractorista worker pivot (Looker)
  GET  /api/tarjas/contratista-tractorista/filters
  GET  /api/tarjas/contratista-tractorista   → Raw tarjas_pagos rows (tractorista only)
"""

import datetime
import decimal
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from psycopg2 import sql as psql

from auth import require_auth
from db import get_connection

logger = logging.getLogger("controllers.tarjas")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_TRACTORISTA_PAGOS_SQL = "(LOWER(TRIM(tipo_pago)) = 'tractorista')"


def _resolve_maquina_column(cur):
    """Return appsheet.tarjas_pagos column for machine/tractor, if any."""
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'appsheet' AND table_name = 'tarjas_pagos'
          AND (
            lower(column_name) IN ('maquina', 'máquina')
            OR lower(column_name) LIKE '%maquin%'
          )
        ORDER BY CASE WHEN lower(column_name) = 'maquina' THEN 0 ELSE 1 END,
                 length(column_name)
        LIMIT 1
        """
    )
    r = cur.fetchone()
    return r[0] if r else None


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def _serialize(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return str(v)
    return v


def _rows_to_dicts(cur):
    cols = [d[0] for d in cur.description]
    return [{k: _serialize(v) for k, v in zip(cols, r)} for r in cur.fetchall()]


# ===========================================================================
# General operacional — Labor averages, person ranking, daily chart
# ===========================================================================

@router.get("/tarjas/general", response_class=HTMLResponse)
async def tarjas_general_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_general.html")


@router.get("/api/tarjas/general/filters")
async def get_tarjas_general_filters():
    """Distinct values for filter dropdowns (from tarjas_pagos)."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT cuartel_cc FROM appsheet.tarjas_pagos "
                "WHERE cuartel_cc IS NOT NULL ORDER BY cuartel_cc"
            )
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT tipo_pago FROM appsheet.tarjas_pagos "
                "WHERE tipo_pago IS NOT NULL ORDER BY tipo_pago"
            )
            tipos_pago = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT labor FROM appsheet.tarjas_pagos "
                "WHERE labor IS NOT NULL ORDER BY labor"
            )
            labores = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "centros_costo": centros_costo,
        "tipos_pago": tipos_pago,
        "labores": labores,
    }


def _build_pagos_where(
    fecha_inicio, fecha_termino, centro_costo, tipo_pago, labor,
    alias="",
):
    """Build WHERE clause + params for tarjas_pagos queries.

    If *alias* is provided (e.g. "p"), column references are prefixed
    with it so the clause is safe inside JOINs.
    """
    pfx = f"{alias}." if alias else ""
    filters = [f"{pfx}fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if centro_costo:
        filters.append(f"{pfx}cuartel_cc = %s")
        params.append(centro_costo)
    if tipo_pago:
        filters.append(f"{pfx}tipo_pago = %s")
        params.append(tipo_pago)
    if labor:
        filters.append(f"{pfx}labor = %s")
        params.append(labor)
    return "WHERE " + " AND ".join(filters), params


@router.get("/api/tarjas/general")
async def get_tarjas_general(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    where, params = _build_pagos_where(
        fecha_inicio, fecha_termino, centro_costo, tipo_pago, labor
    )

    try:
        with conn.cursor() as cur:
            # 1) Average earnings per labor
            cur.execute(f"""
                SELECT
                    labor,
                    ROUND(AVG(total_trabajado)::numeric, 2) AS avg_rate,
                    COALESCE(SUM(total_trabajado), 0)       AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY labor
                ORDER BY total DESC
            """, params)
            labor_summary = _rows_to_dicts(cur)

            # 2) Person ranking (top earners)
            cur.execute(f"""
                SELECT
                    trabajador,
                    contratista,
                    ROUND(AVG(total_trabajado)::numeric, 2) AS avg_rate,
                    COALESCE(SUM(total_trabajado), 0)       AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY trabajador, contratista
                ORDER BY total DESC
            """, params)
            person_ranking = _rows_to_dicts(cur)

            # 3) Daily average by labor × cuadrilla (top 6 workers)
            p_where, p_params = _build_pagos_where(
                fecha_inicio, fecha_termino, centro_costo, tipo_pago, labor,
                alias="p",
            )
            cur.execute(f"""
                WITH top_workers AS (
                    SELECT trabajador
                    FROM appsheet.tarjas_pagos
                    {where}
                    GROUP BY trabajador
                    ORDER BY SUM(total_trabajado) DESC
                    LIMIT 6
                )
                SELECT
                    p.labor,
                    p.trabajador,
                    ROUND(AVG(p.total_trabajado)::numeric, 2) AS avg_daily
                FROM appsheet.tarjas_pagos p
                JOIN top_workers tw ON tw.trabajador = p.trabajador
                {p_where}
                GROUP BY p.labor, p.trabajador
                ORDER BY p.labor, avg_daily DESC
            """, params + p_params)
            chart_data = _rows_to_dicts(cur)
    finally:
        conn.close()

    return {
        "labor_summary": labor_summary,
        "person_ranking": person_ranking,
        "chart_data": chart_data,
    }


# ===========================================================================
# Detalle semanal
# ===========================================================================

@router.get("/tarjas/detalle", response_class=HTMLResponse)
async def tarjas_detail_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_detail.html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@router.get("/api/tarjas/detalle/filters")
async def get_tarjas_filters():
    """Distinct values for each filter dropdown."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT contratista FROM appsheet.tarjas_reporte ORDER BY contratista')
            contratistas = [r[0] for r in cur.fetchall()]

            cur.execute('SELECT DISTINCT "CC" FROM appsheet.tarjas_reporte WHERE "CC" IS NOT NULL ORDER BY "CC"')
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute('SELECT DISTINCT "Nombre Labor" FROM appsheet.tarjas_reporte ORDER BY "Nombre Labor"')
            labores = [r[0] for r in cur.fetchall()]

            cur.execute('SELECT DISTINCT nombre_campo FROM appsheet.tarjas_reporte ORDER BY nombre_campo')
            campos = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "contratistas": contratistas,
        "centros_costo": centros_costo,
        "labores": labores,
        "campos": campos,
    }


@router.get("/api/tarjas/detalle")
async def get_tarjas_detail(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
    campo: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if centro_costo:
        filters.append('"CC" = %s')
        params.append(centro_costo)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)
    if labor:
        filters.append('"Nombre Labor" = %s')
        params.append(labor)
    if campo:
        filters.append("nombre_campo = %s")
        params.append(campo)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            # Summary by tipo_pago
            cur.execute(f"""
                SELECT
                    tipo_pago,
                    COALESCE(SUM(total_labor), 0) AS total_pagar,
                    COALESCE(SUM(jornadas), 0)    AS jornadas
                FROM appsheet.tarjas_reporte
                {where}
                GROUP BY tipo_pago
                ORDER BY tipo_pago
            """, params)
            resumen = _rows_to_dicts(cur)

            # Detail rows
            cur.execute(f"""
                SELECT
                    tipo_pago,
                    "CC"              AS centro_costo,
                    "Nombre Labor"    AS labor,
                    jornadas,
                    total_unitario,
                    total_labor       AS costo_total,
                    "%% Tipo de pago" AS pct_pago,
                    contratista,
                    nombre_campo,
                    fecha::text       AS fecha
                FROM appsheet.tarjas_reporte
                {where}
                ORDER BY tipo_pago DESC, "CC", "Nombre Labor"
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    total_general = sum(r["total_pagar"] for r in resumen)
    jornadas_general = sum(r["jornadas"] for r in resumen)

    return {
        "resumen": resumen,
        "total": total_general,
        "jornadas": jornadas_general,
        "rows": rows,
        "count": len(rows),
    }


# ===========================================================================
# Detalle de la semana tractorista (Looker: Detalle tractorista)
# ===========================================================================

_TRACTORISTA_SQL = "(LOWER(TRIM(tipo_pago)) = 'tractorista')"


@router.get("/tarjas/detalle-tractorista", response_class=HTMLResponse)
async def tarjas_detalle_tractorista_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_detalle_tractorista.html")


@router.get("/tractoristas")
async def redirect_tractoristas_legacy():
    """Old menu URL → weekly tractorista detail."""
    return RedirectResponse(url="/tarjas/detalle-tractorista", status_code=302)


@router.get("/api/tarjas/detalle-tractorista/filters")
async def get_tarjas_detalle_tractorista_filters():
    """Filter options limited to Tractorista rows in tarjas_reporte."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT DISTINCT contratista FROM appsheet.tarjas_reporte '
                f'WHERE {_TRACTORISTA_SQL} ORDER BY contratista'
            )
            contratistas = [r[0] for r in cur.fetchall()]

            cur.execute(
                f'SELECT DISTINCT "CC" FROM appsheet.tarjas_reporte '
                f'WHERE {_TRACTORISTA_SQL} AND "CC" IS NOT NULL ORDER BY "CC"'
            )
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute(
                f'SELECT DISTINCT "Nombre Labor" FROM appsheet.tarjas_reporte '
                f'WHERE {_TRACTORISTA_SQL} ORDER BY "Nombre Labor"'
            )
            labores = [r[0] for r in cur.fetchall()]

            cur.execute(
                f'SELECT DISTINCT nombre_campo FROM appsheet.tarjas_reporte '
                f'WHERE {_TRACTORISTA_SQL} ORDER BY nombre_campo'
            )
            campos = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "contratistas": contratistas,
        "centros_costo": centros_costo,
        "labores": labores,
        "campos": campos,
    }


@router.get("/api/tarjas/detalle-tractorista")
async def get_tarjas_detalle_tractorista(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    centro_costo: str = Query(None),
    labor: str = Query(None),
    campo: str = Query(None),
):
    """Weekly tractorista report: summary by contractor + detail rows."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha BETWEEN %s AND %s", _TRACTORISTA_SQL]
    params: list = [fecha_inicio, fecha_termino]

    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if centro_costo:
        filters.append('"CC" = %s')
        params.append(centro_costo)
    if labor:
        filters.append('"Nombre Labor" = %s')
        params.append(labor)
    if campo:
        filters.append("nombre_campo = %s")
        params.append(campo)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    tipo_pago,
                    contratista,
                    COALESCE(SUM(total_labor), 0) AS total_pagar,
                    COALESCE(SUM(jornadas), 0)    AS jornadas
                FROM appsheet.tarjas_reporte
                {where}
                GROUP BY tipo_pago, contratista
                ORDER BY contratista
            """, params)
            resumen_contratista = _rows_to_dicts(cur)

            cur.execute(f"""
                SELECT
                    tipo_pago,
                    "CC"              AS centro_costo,
                    "Nombre Labor"    AS labor,
                    jornadas,
                    total_unitario,
                    total_labor       AS costo_total,
                    contratista,
                    nombre_campo,
                    fecha::text       AS fecha
                FROM appsheet.tarjas_reporte
                {where}
                ORDER BY contratista, fecha::date, "CC", "Nombre Labor"
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    total_general = sum(r["total_pagar"] for r in resumen_contratista)
    jornadas_general = sum(r["jornadas"] for r in resumen_contratista)

    return {
        "resumen_contratista": resumen_contratista,
        "total": total_general,
        "jornadas": jornadas_general,
        "rows": rows,
        "count": len(rows),
    }


# ===========================================================================
# Detalle Contratista — Pivot by worker × date
# ===========================================================================

@router.get("/tarjas/contratista", response_class=HTMLResponse)
async def tarjas_contractor_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_contractor.html")


@router.get("/api/tarjas/contratista/filters")
async def get_tarjas_contractor_filters():
    """Distinct values for each filter dropdown (from tarjas_pagos directly)."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT contratista FROM appsheet.tarjas_pagos "
                "WHERE contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT cuartel_cc FROM appsheet.tarjas_pagos "
                "WHERE cuartel_cc IS NOT NULL ORDER BY cuartel_cc"
            )
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT labor FROM appsheet.tarjas_pagos "
                "WHERE labor IS NOT NULL ORDER BY labor"
            )
            labores = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT tipo_pago FROM appsheet.tarjas_pagos "
                "WHERE tipo_pago IS NOT NULL ORDER BY tipo_pago"
            )
            tipos_pago = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "contratistas": contratistas,
        "centros_costo": centros_costo,
        "labores": labores,
        "tipos_pago": tipos_pago,
    }


@router.get("/api/tarjas/contratista")
async def get_tarjas_contractor_data(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
):
    """Return raw tarjas_pagos rows for the pivot table."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if centro_costo:
        filters.append("cuartel_cc = %s")
        params.append(centro_costo)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)
    if labor:
        filters.append("labor = %s")
        params.append(labor)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT *, fecha::date::text AS fecha "
                f"FROM appsheet.tarjas_pagos {where} "
                "ORDER BY contratista, labor, fecha::date",
                params,
            )
            cols = [d[0] for d in cur.description]
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    return {
        "columns": cols,
        "rows": rows,
        "count": len(rows),
    }


# ===========================================================================
# Por persona Tractorista — Worker pivot (tractorista only, Looker)
# ===========================================================================

@router.get("/tarjas/contratista-tractorista", response_class=HTMLResponse)
async def tarjas_contractor_tractorista_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_contractor_tractorista.html")


@router.get("/api/tarjas/contratista-tractorista/filters")
async def get_tarjas_contractor_tractorista_filters():
    """Filter options from tarjas_pagos limited to Tractorista rows."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            maq_col = _resolve_maquina_column(cur)
            base_where = f" FROM appsheet.tarjas_pagos WHERE {_TRACTORISTA_PAGOS_SQL} "

            cur.execute(
                "SELECT DISTINCT contratista " + base_where +
                "AND contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT cuartel_cc " + base_where +
                "AND cuartel_cc IS NOT NULL ORDER BY cuartel_cc"
            )
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT labor " + base_where +
                "AND labor IS NOT NULL ORDER BY labor"
            )
            labores = [r[0] for r in cur.fetchall()]

            maquinas = []
            if maq_col:
                cur.execute(
                    psql.SQL(
                        "SELECT DISTINCT {col} FROM appsheet.tarjas_pagos WHERE "
                        + _TRACTORISTA_PAGOS_SQL
                        + " AND {col} IS NOT NULL ORDER BY {col}"
                    ).format(col=psql.Identifier(maq_col))
                )
                maquinas = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "contratistas": contratistas,
        "centros_costo": centros_costo,
        "labores": labores,
        "maquinas": maquinas,
        "maquina_column": maq_col,
    }


@router.get("/api/tarjas/contratista-tractorista")
async def get_tarjas_contractor_tractorista_data(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    centro_costo: str = Query(None),
    labor: str = Query(None),
    maquina: str = Query(None),
):
    """Raw tarjas_pagos rows for the tractorista contractor pivot."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]

    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if centro_costo:
        filters.append("cuartel_cc = %s")
        params.append(centro_costo)
    if labor:
        filters.append("labor = %s")
        params.append(labor)

    try:
        with conn.cursor() as cur:
            maq_col = _resolve_maquina_column(cur)
            if maq_col and maquina is not None and maquina != "":
                frag = psql.SQL("{} = %s").format(psql.Identifier(maq_col))
                filters.append(frag.as_string(conn))
                params.append(maquina)

            where = "WHERE " + " AND ".join(filters)
            cur.execute(
                f"SELECT *, fecha::date::text AS fecha "
                f"FROM appsheet.tarjas_pagos {where} "
                "ORDER BY contratista, labor, fecha::date",
                params,
            )
            cols = [d[0] for d in cur.description]
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    return {
        "columns": cols,
        "rows": rows,
        "count": len(rows),
    }


# ===========================================================================
# Resumen por persona operacional — Worker summary pivot (worker × date)
# ===========================================================================

@router.get("/tarjas/resumen-persona", response_class=HTMLResponse)
async def tarjas_resumen_persona_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_resumen_persona.html")


@router.get("/api/tarjas/resumen-persona/filters")
async def get_tarjas_resumen_persona_filters():
    """Distinct trabajador + tipo_pago for filter dropdowns."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trabajador, COALESCE(SUM(total_trabajado), 0) AS total "
                "FROM appsheet.tarjas_pagos "
                "WHERE trabajador IS NOT NULL "
                "GROUP BY trabajador ORDER BY total DESC"
            )
            trabajadores = _rows_to_dicts(cur)

            cur.execute(
                "SELECT DISTINCT tipo_pago FROM appsheet.tarjas_pagos "
                "WHERE tipo_pago IS NOT NULL ORDER BY tipo_pago"
            )
            tipos_pago = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "trabajadores": trabajadores,
        "tipos_pago": tipos_pago,
    }


@router.get("/api/tarjas/resumen-persona")
async def get_tarjas_resumen_persona(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    trabajador: str = Query(None),
    tipo_pago: str = Query(None),
):
    """Return worker-level rows for the resumen pivot table."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if trabajador:
        filters.append("trabajador = %s")
        params.append(trabajador)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(total_trabajado), 0) AS total_trabajado "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, tipo_pago, fecha::date "
                "ORDER BY trabajador, tipo_pago, fecha::date",
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    return {
        "rows": rows,
        "count": len(rows),
    }


# ===========================================================================
# Resumen hora extra por persona — Worker hours pivot (worker × date)
# ===========================================================================

@router.get("/tarjas/resumen-horas", response_class=HTMLResponse)
async def tarjas_resumen_horas_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_resumen_horas.html")


@router.get("/api/tarjas/resumen-horas/filters")
async def get_tarjas_resumen_horas_filters():
    """Distinct trabajador + tipo_pago for the hours report."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trabajador, COALESCE(SUM(horas_trabajadas), 0)::int AS total "
                "FROM appsheet.tarjas_pagos "
                "WHERE trabajador IS NOT NULL "
                "GROUP BY trabajador ORDER BY total DESC"
            )
            trabajadores = _rows_to_dicts(cur)

            cur.execute(
                "SELECT DISTINCT tipo_pago FROM appsheet.tarjas_pagos "
                "WHERE tipo_pago IS NOT NULL ORDER BY tipo_pago"
            )
            tipos_pago = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "trabajadores": trabajadores,
        "tipos_pago": tipos_pago,
    }


@router.get("/api/tarjas/resumen-horas")
async def get_tarjas_resumen_horas(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    trabajador: str = Query(None),
    tipo_pago: str = Query(None),
):
    """Return worker hours grouped by date for the pivot table."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if trabajador:
        filters.append("trabajador = %s")
        params.append(trabajador)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(horas_trabajadas), 0)::int AS horas_trabajadas "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, tipo_pago, fecha::date "
                "ORDER BY trabajador, tipo_pago, fecha::date",
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    return {
        "rows": rows,
        "count": len(rows),
    }


# ===========================================================================
# Resumen por persona tractorista — Worker × date pivot (total_tractor)
# ===========================================================================

@router.get("/tarjas/resumen-persona-tractorista", response_class=HTMLResponse)
async def tarjas_resumen_persona_tractorista_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_resumen_persona_tractorista.html")


@router.get("/api/tarjas/resumen-persona-tractorista/filters")
async def get_tarjas_resumen_persona_tractorista_filters():
    """Filter options for the tractorista worker pivot."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            maq_col = _resolve_maquina_column(cur)

            cur.execute(
                "SELECT trabajador, COALESCE(SUM(total_tractor), 0) AS total "
                "FROM appsheet.tarjas_pagos "
                f"WHERE {_TRACTORISTA_PAGOS_SQL} AND trabajador IS NOT NULL "
                "GROUP BY trabajador ORDER BY total DESC"
            )
            trabajadores = _rows_to_dicts(cur)

            cur.execute(
                "SELECT DISTINCT tipo_pago FROM appsheet.tarjas_pagos "
                f"WHERE {_TRACTORISTA_PAGOS_SQL} AND tipo_pago IS NOT NULL ORDER BY tipo_pago"
            )
            tipos_pago = [r[0] for r in cur.fetchall()]

            maquinas = []
            if maq_col:
                cur.execute(
                    psql.SQL(
                        "SELECT DISTINCT {col} FROM appsheet.tarjas_pagos WHERE "
                        + _TRACTORISTA_PAGOS_SQL
                        + " AND {col} IS NOT NULL ORDER BY {col}"
                    ).format(col=psql.Identifier(maq_col))
                )
                maquinas = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "trabajadores": trabajadores,
        "tipos_pago": tipos_pago,
        "maquinas": maquinas,
        "maquina_column": maq_col,
    }


@router.get("/api/tarjas/resumen-persona-tractorista")
async def get_tarjas_resumen_persona_tractorista(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    trabajador: str = Query(None),
    tipo_pago: str = Query(None),
    maquina: str = Query(None),
):
    """Worker × date pivot rows using total_tractor (tractorista only)."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]

    if trabajador:
        filters.append("trabajador = %s")
        params.append(trabajador)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)

    try:
        with conn.cursor() as cur:
            maq_col = _resolve_maquina_column(cur)
            if maq_col and maquina:
                frag = psql.SQL("{} = %s").format(psql.Identifier(maq_col))
                filters.append(frag.as_string(conn))
                params.append(maquina)

            maq_select = psql.SQL(", {col} AS maquina").format(
                col=psql.Identifier(maq_col)
            ).as_string(conn) if maq_col else ", NULL AS maquina"

            where = "WHERE " + " AND ".join(filters)

            cur.execute(
                f"SELECT trabajador{maq_select}, horas_extras, "
                f"fecha::date::text AS fecha, "
                f"COALESCE(SUM(total_tractor), 0) AS total_tractor "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, maquina, horas_extras, fecha::date "
                "ORDER BY trabajador, maquina, fecha::date",
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    return {
        "rows": rows,
        "count": len(rows),
    }


# ===========================================================================
# General Tractorista — Labor averages, person ranking, daily chart (tractorista only)
# ===========================================================================

@router.get("/tarjas/general-tractorista", response_class=HTMLResponse)
async def tarjas_general_tractorista_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_general_tractorista.html")


@router.get("/api/tarjas/general-tractorista/filters")
async def get_tarjas_general_tractorista_filters():
    """Distinct filter values for General Tractorista (tractorista rows only)."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            maq_col = _resolve_maquina_column(cur)
            base = f" FROM appsheet.tarjas_pagos WHERE {_TRACTORISTA_PAGOS_SQL} "

            cur.execute(
                "SELECT DISTINCT cuartel_cc " + base
                + "AND cuartel_cc IS NOT NULL ORDER BY cuartel_cc"
            )
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT labor " + base
                + "AND labor IS NOT NULL ORDER BY labor"
            )
            labores = [r[0] for r in cur.fetchall()]

            maquinas = []
            if maq_col:
                cur.execute(
                    psql.SQL(
                        "SELECT DISTINCT {col} FROM appsheet.tarjas_pagos WHERE "
                        + _TRACTORISTA_PAGOS_SQL
                        + " AND {col} IS NOT NULL ORDER BY {col}"
                    ).format(col=psql.Identifier(maq_col))
                )
                maquinas = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {
        "centros_costo": centros_costo,
        "labores": labores,
        "maquinas": maquinas,
        "maquina_column": maq_col,
    }


@router.get("/api/tarjas/general-tractorista")
async def get_tarjas_general_tractorista(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    centro_costo: str = Query(None),
    labor: str = Query(None),
    maquina: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]

    if centro_costo:
        filters.append("cuartel_cc = %s")
        params.append(centro_costo)
    if labor:
        filters.append("labor = %s")
        params.append(labor)

    try:
        with conn.cursor() as cur:
            maq_col = _resolve_maquina_column(cur)
            if maq_col and maquina:
                frag = psql.SQL("{} = %s").format(psql.Identifier(maq_col))
                filters.append(frag.as_string(conn))
                params.append(maquina)

            where = "WHERE " + " AND ".join(filters)

            # 1) Average earnings per labor — tractoristas use total_tractor
            cur.execute(f"""
                SELECT
                    labor,
                    ROUND(AVG(total_tractor)::numeric, 2) AS avg_rate,
                    COALESCE(SUM(total_tractor), 0)       AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY labor
                ORDER BY total DESC
            """, params)
            labor_summary = _rows_to_dicts(cur)

            # 2) Person ranking
            cur.execute(f"""
                SELECT
                    trabajador,
                    contratista,
                    ROUND(AVG(total_tractor)::numeric, 2) AS avg_rate,
                    COALESCE(SUM(total_tractor), 0)       AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY trabajador, contratista
                ORDER BY total DESC
            """, params)
            person_ranking = _rows_to_dicts(cur)

            # 3) Daily average by labor × worker (top 6)
            cur.execute(f"""
                WITH top_workers AS (
                    SELECT trabajador
                    FROM appsheet.tarjas_pagos
                    {where}
                    GROUP BY trabajador
                    ORDER BY SUM(total_tractor) DESC
                    LIMIT 6
                )
                SELECT
                    p.labor,
                    p.trabajador,
                    ROUND(AVG(p.total_tractor)::numeric, 2) AS avg_daily
                FROM appsheet.tarjas_pagos p
                JOIN top_workers tw ON tw.trabajador = p.trabajador
                WHERE p.fecha::date BETWEEN %s AND %s
                  AND {_TRACTORISTA_PAGOS_SQL.replace('tipo_pago', 'p.tipo_pago')}
                GROUP BY p.labor, p.trabajador
                ORDER BY p.labor, avg_daily DESC
            """, params + [fecha_inicio, fecha_termino])
            chart_data = _rows_to_dicts(cur)
    finally:
        conn.close()

    return {
        "labor_summary": labor_summary,
        "person_ranking": person_ranking,
        "chart_data": chart_data,
    }
