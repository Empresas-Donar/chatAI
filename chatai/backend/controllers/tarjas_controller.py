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

  GET  /tarjas/notas                    → Notas de crédito page (contractor payment report)
  GET  /api/tarjas/notas/filters        → Filter options (notas)
  GET  /api/tarjas/notas                → Report data
"""

import csv
import datetime
import decimal
import io
import logging
import re

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from xhtml2pdf import pisa

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from psycopg2 import sql as psql

from auth import require_auth
from db import get_connection

logger = logging.getLogger("controllers.tarjas")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_TRACTORISTA_PAGOS_SQL = "(LOWER(TRIM(tipo_pago)) = 'tractorista')"

def _empresa_to_campo(empresa: str | None) -> str | None:
    return empresa or None


def _get_empresas(cur, table: str = "appsheet.tarjas_pagos", extra_where: str = "") -> list[str]:
    """Return distinct nombre_campo values as empresa options."""
    where = f"WHERE nombre_campo IS NOT NULL {('AND ' + extra_where) if extra_where else ''}"
    cur.execute(f"SELECT DISTINCT nombre_campo FROM {table} {where} ORDER BY nombre_campo")
    return [r[0] for r in cur.fetchall()]


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
# PDF helpers
# ===========================================================================

_PDF_CSS = """
@page { size: A4 landscape; margin: 12mm 10mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 8pt; color: #1a1a1a; margin: 0; }
.ph { background: #1A1208; color: #F2C04A; padding: 8px 12px; margin-bottom: 12px; }
.ph h1 { font-size: 13pt; font-weight: bold; color: #F2C04A; margin: 0 0 3px 0; }
.ph-sub { font-size: 7.5pt; color: #C4A870; margin: 0; }
.ph-chips { background: #2E1D08; padding: 5px 12px; margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 5px; }
.chip { background: #3D2D10; border: 1px solid #5a4020; border-radius: 3px; padding: 2px 7px; font-size: 7pt; color: #e8d5a0; }
.chip b { color: #F2C04A; }
table { width: 100%; border-collapse: collapse; font-size: 7.5pt; }
th { background: #1A1208; color: #F2C04A; padding: 5px 6px; text-align: left; border: 1px solid #3D2D10; font-weight: bold; }
th.num { text-align: right; }
td { padding: 3px 6px; border: 1px solid #ddd; vertical-align: middle; }
tr:nth-child(even) td { background: #faf8f5; }
tr.worker-first td { border-top: 1.5px solid #F2C04A; }
.num { text-align: right; }
.total { text-align: right; font-weight: bold; background: #fdf6e3; border-left: 1.5px solid #F2C04A; }
.section-title { font-size: 9pt; font-weight: bold; margin: 12px 0 5px 0; color: #1A1208; }
"""

def _pdf_header(title: str, fecha_inicio: str, fecha_termino: str, filters: dict) -> str:
    now = datetime.date.today().strftime("%-d de %B de %Y")
    chips = ""
    for k, v in filters.items():
        if v:
            chips += f'<span class="chip"><b>{k}:</b> {v}</span> '
    return f"""
    <div class="ph">
      <h1>{title}</h1>
      <p class="ph-sub">Generado el {now}</p>
    </div>
    <div class="ph-chips">
      <span class="chip"><b>Desde:</b> {fecha_inicio}</span>
      <span class="chip"><b>Hasta:</b> {fecha_termino}</span>
      {chips}
    </div>
    """

def _render_pdf(html: str, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html), dest=buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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

            cur.execute(
                "SELECT DISTINCT contratista FROM appsheet.tarjas_pagos "
                "WHERE contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]
            empresas = _get_empresas(cur, "appsheet.tarjas_pagos")
    finally:
        conn.close()

    return {
        "centros_costo": centros_costo,
        "tipos_pago": tipos_pago,
        "labores": labores,
        "contratistas": contratistas,
        "empresas": empresas,
    }


def _build_pagos_where(
    fecha_inicio, fecha_termino, centro_costo, tipo_pago, labor,
    alias="", contratista=None, nombre_campo=None,
):
    """Build WHERE clause + params for tarjas_pagos queries."""
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
    if contratista:
        filters.append(f"{pfx}contratista = %s")
        params.append(contratista)
    if nombre_campo:
        filters.append(f"{pfx}nombre_campo = %s")
        params.append(nombre_campo)
    return "WHERE " + " AND ".join(filters), params


@router.get("/api/tarjas/general")
async def get_tarjas_general(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    where, params = _build_pagos_where(
        fecha_inicio, fecha_termino, centro_costo, tipo_pago, labor,
        contratista=contratista, nombre_campo=_empresa_to_campo(empresa),
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
                alias="p", contratista=contratista,
                nombre_campo=_empresa_to_campo(empresa),
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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
            empresas = _get_empresas(cur, "appsheet.tarjas_reporte")
    finally:
        conn.close()

    return {
        "contratistas": contratistas,
        "empresas": empresas,
        "centros_costo": centros_costo,
        "labores": labores,
        "campos": campos,
    }


@router.get("/api/tarjas/detalle")
async def get_tarjas_detail(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    empresa: str = Query(None),
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))
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
                    "Nombre Labor"    AS labor,
                    "CC"              AS centro_costo,
                    jornadas,
                    total_unitario,
                    total_labor       AS costo_total,
                    CASE WHEN jornadas > 0 THEN ROUND((total_labor / jornadas)::numeric, 0) ELSE NULL END AS costo_hora,
                    "%% Tipo de pago" AS pct_pago,
                    nombre_campo,
                    fecha::text       AS fecha
                FROM appsheet.tarjas_reporte
                {where}
                ORDER BY tipo_pago DESC, "Nombre Labor", "CC"
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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
            empresas = _get_empresas(cur, "appsheet.tarjas_reporte", extra_where="LOWER(TRIM(tipo_pago)) = 'tractorista'")
    finally:
        conn.close()

    return {
        "contratistas": contratistas,
        "empresas": empresas,
        "centros_costo": centros_costo,
        "labores": labores,
        "campos": campos,
    }


@router.get("/api/tarjas/detalle-tractorista")
async def get_tarjas_detalle_tractorista(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    empresa: str = Query(None),
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha BETWEEN %s AND %s", _TRACTORISTA_SQL]
    params: list = [fecha_inicio, fecha_termino]

    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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
            empresas = _get_empresas(cur, "appsheet.tarjas_pagos")
    finally:
        conn.close()

    return {
        "contratistas": contratistas,
        "empresas": empresas,
        "centros_costo": centros_costo,
        "labores": labores,
        "tipos_pago": tipos_pago,
    }


@router.get("/api/tarjas/contratista")
async def get_tarjas_contractor_data(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    empresa: str = Query(None),
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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
            empresas = _get_empresas(cur, "appsheet.tarjas_pagos", extra_where="LOWER(TRIM(tipo_pago)) = 'tractorista'")
    finally:
        conn.close()

    return {
        "contratistas": contratistas,
        "empresas": empresas,
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
    empresa: str = Query(None),
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]

    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))
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
    """Distinct trabajador + tipo_pago + contratista for filter dropdowns."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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

            cur.execute(
                "SELECT DISTINCT contratista FROM appsheet.tarjas_pagos "
                "WHERE contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]
            empresas = _get_empresas(cur, "appsheet.tarjas_pagos")
    finally:
        conn.close()

    return {
        "trabajadores": trabajadores,
        "tipos_pago": tipos_pago,
        "contratistas": contratistas,
        "empresas": empresas,
    }


@router.get("/api/tarjas/resumen-persona")
async def get_tarjas_resumen_persona(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    trabajador: str = Query(None),
    tipo_pago: str = Query(None),
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    """Return worker-level rows for the resumen pivot table."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if trabajador:
        filters.append("trabajador = %s")
        params.append(trabajador)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))

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


@router.get("/api/tarjas/resumen-persona/download-excel")
async def download_tarjas_resumen_persona_excel(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    trabajador: str = Query(None),
    tipo_pago: str = Query(None),
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    """Descarga la tabla pivot resumen-persona como Excel."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if trabajador:
        filters.append("trabajador = %s")
        params.append(trabajador)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, contratista, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(total_trabajado), 0) AS total_trabajado "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, contratista, tipo_pago, fecha::date "
                "ORDER BY trabajador, tipo_pago, fecha::date",
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    # Build pivot: worker+tipo → date → total
    dates = sorted({r["fecha"] for r in rows})

    workers: dict = {}
    for r in rows:
        key = (r["trabajador"] or "", r["contratista"] or "", r["tipo_pago"] or "")
        if key not in workers:
            workers[key] = {"by_date": {}, "total": 0}
        workers[key]["by_date"][r["fecha"]] = (
            workers[key]["by_date"].get(r["fecha"], 0) + float(r["total_trabajado"] or 0)
        )
        workers[key]["total"] += float(r["total_trabajado"] or 0)

    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resumen por persona"

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF")
    total_fill = PatternFill("solid", fgColor="D6E4F0")
    money_fmt = '#,##0'

    # Header row
    headers = ["Trabajador", "Contratista", "Tipo de pago"] + [
        datetime.date.fromisoformat(d).strftime("%-d %b %Y") for d in dates
    ] + ["Total"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    row_num = 2
    for (trab, cont, tipo), entry in sorted_workers:
        ws.cell(row=row_num, column=1, value=trab)
        ws.cell(row=row_num, column=2, value=cont)
        ws.cell(row=row_num, column=3, value=tipo)
        for col, d in enumerate(dates, 4):
            val = entry["by_date"].get(d, 0)
            c = ws.cell(row=row_num, column=col, value=val if val else None)
            c.number_format = money_fmt
        total_cell = ws.cell(row=row_num, column=4 + len(dates), value=entry["total"])
        total_cell.number_format = money_fmt
        total_cell.fill = total_fill
        total_cell.font = Font(bold=True)
        row_num += 1

    # Column widths
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 18
    for i in range(len(dates) + 1):
        col_letter = openpyxl.utils.get_column_letter(4 + i)
        ws.column_dimensions[col_letter].width = 14

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"resumen_persona_{fecha_inicio}_{fecha_termino}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===========================================================================
# Resumen hora extra por persona — Worker hours pivot (worker × date)
# ===========================================================================

@router.get("/tarjas/resumen-horas", response_class=HTMLResponse)
async def tarjas_resumen_horas_page(request: Request):
    return _templates.TemplateResponse(request, "tarjas_resumen_horas.html")


@router.get("/api/tarjas/resumen-horas/filters")
async def get_tarjas_resumen_horas_filters():
    """Distinct trabajador + tipo_pago + contratista for the hours report."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trabajador, COALESCE(SUM(horas_trabajadas::numeric), 0)::int AS total "
                "FROM appsheet.tarjas_pagos "
                "WHERE trabajador IS NOT NULL AND horas_trabajadas ~ '^[0-9]+(\\.[0-9]+)?$' "
                "GROUP BY trabajador ORDER BY total DESC"
            )
            trabajadores = _rows_to_dicts(cur)

            cur.execute(
                "SELECT DISTINCT tipo_pago FROM appsheet.tarjas_pagos "
                "WHERE tipo_pago IS NOT NULL ORDER BY tipo_pago"
            )
            tipos_pago = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT contratista FROM appsheet.tarjas_pagos "
                "WHERE contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]
            empresas = _get_empresas(cur, "appsheet.tarjas_pagos")
    finally:
        conn.close()

    return {
        "trabajadores": trabajadores,
        "tipos_pago": tipos_pago,
        "contratistas": contratistas,
        "empresas": empresas,
    }


@router.get("/api/tarjas/resumen-horas")
async def get_tarjas_resumen_horas(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    trabajador: str = Query(None),
    tipo_pago: str = Query(None),
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    """Return worker hours grouped by date for the pivot table."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if trabajador:
        filters.append("trabajador = %s")
        params.append(trabajador)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\\.[0-9]+)?$' "
                f"THEN horas_trabajadas::numeric ELSE 0 END), 0)::int AS horas_trabajadas "
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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

            cur.execute(
                "SELECT DISTINCT contratista FROM appsheet.tarjas_pagos "
                f"WHERE {_TRACTORISTA_PAGOS_SQL} AND contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]

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
            empresas = _get_empresas(cur, "appsheet.tarjas_pagos", extra_where="LOWER(TRIM(tipo_pago)) = 'tractorista'")
    finally:
        conn.close()

    return {
        "trabajadores": trabajadores,
        "tipos_pago": tipos_pago,
        "contratistas": contratistas,
        "empresas": empresas,
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
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    """Worker × date pivot rows using total_tractor (tractorista only)."""
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]

    if trabajador:
        filters.append("trabajador = %s")
        params.append(trabajador)
    if tipo_pago:
        filters.append("tipo_pago = %s")
        params.append(tipo_pago)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))

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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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

            cur.execute(
                "SELECT DISTINCT contratista " + base
                + "AND contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]

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
            empresas = _get_empresas(cur, "appsheet.tarjas_pagos", extra_where="LOWER(TRIM(tipo_pago)) = 'tractorista'")
    finally:
        conn.close()

    return {
        "centros_costo": centros_costo,
        "labores": labores,
        "contratistas": contratistas,
        "empresas": empresas,
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
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]

    if centro_costo:
        filters.append("cuartel_cc = %s")
        params.append(centro_costo)
    if labor:
        filters.append("labor = %s")
        params.append(labor)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))

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


# ===========================================================================
# Excel download helpers
# ===========================================================================

def _excel_response(wb: "openpyxl.Workbook", filename: str) -> StreamingResponse:
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _excel_header_style():
    from openpyxl.styles import Font, PatternFill, Alignment
    fill = PatternFill("solid", fgColor="1F4E79")
    font = Font(bold=True, color="FFFFFF")
    align = Alignment(horizontal="center")
    return fill, font, align


def _apply_header(ws, headers):
    fill, font, align = _excel_header_style()
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.fill = fill; c.font = font; c.alignment = align


@router.get("/api/tarjas/general/download-excel")
async def download_tarjas_general_excel(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    where, params = _build_pagos_where(
        fecha_inicio, fecha_termino, centro_costo, tipo_pago, labor,
        contratista=contratista, nombre_campo=_empresa_to_campo(empresa),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT trabajador, contratista, labor, tipo_pago,
                       ROUND(AVG(total_trabajado)::numeric,2) AS promedio,
                       COALESCE(SUM(total_trabajado),0) AS total
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista, labor, tipo_pago
                ORDER BY total DESC
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "General"
    _apply_header(ws, ["Trabajador", "Contratista", "Labor", "Tipo de pago", "Promedio", "Total"])
    money = '#,##0'; money2 = '#,##0.00'
    for i, r in enumerate(rows, 2):
        ws.cell(i, 1, r["trabajador"]); ws.cell(i, 2, r["contratista"])
        ws.cell(i, 3, r["labor"]); ws.cell(i, 4, r["tipo_pago"])
        c5 = ws.cell(i, 5, float(r["promedio"] or 0)); c5.number_format = money2
        c6 = ws.cell(i, 6, float(r["total"] or 0)); c6.number_format = money
    for col, w in zip("ABCDEF", [28, 24, 28, 16, 14, 14]):
        ws.column_dimensions[col].width = w
    return _excel_response(wb, f"tarjas_general_{fecha_inicio}_{fecha_termino}.xlsx")


@router.get("/api/tarjas/detalle/download-excel")
async def download_tarjas_detalle_excel(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    empresa: str = Query(None),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
    campo: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    filters = ["fecha BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    if centro_costo: filters.append('"CC" = %s'); params.append(centro_costo)
    if tipo_pago: filters.append("tipo_pago = %s"); params.append(tipo_pago)
    if labor: filters.append('"Nombre Labor" = %s'); params.append(labor)
    if campo: filters.append("nombre_campo = %s"); params.append(campo)
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT tipo_pago, "Nombre Labor" AS labor, "CC" AS centro_costo,
                       jornadas, total_unitario, total_labor AS costo_total,
                       CASE WHEN jornadas > 0 THEN ROUND((total_labor / jornadas)::numeric, 0) ELSE NULL END AS costo_hora,
                       "%% Tipo de pago" AS pct_pago, nombre_campo, fecha::text AS fecha
                FROM appsheet.tarjas_reporte {where}
                ORDER BY tipo_pago DESC, "Nombre Labor", "CC"
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Detalle"
    _apply_header(ws, ["Tipo de pago", "Labor", "CC", "Jornadas", "Total unitario",
                        "Costo total", "Costo por hora", "% Tipo pago", "Campo", "Fecha"])
    money = '#,##0'
    for i, r in enumerate(rows, 2):
        ws.cell(i,1,r["tipo_pago"]); ws.cell(i,2,r["labor"]); ws.cell(i,3,r["centro_costo"])
        ws.cell(i,4,r["jornadas"])
        c5=ws.cell(i,5,float(r["total_unitario"] or 0)); c5.number_format=money
        c6=ws.cell(i,6,float(r["costo_total"] or 0)); c6.number_format=money
        c7=ws.cell(i,7,float(r["costo_hora"] or 0) if r["costo_hora"] is not None else None); c7.number_format=money
        ws.cell(i,8,float(r["pct_pago"] or 0))
        ws.cell(i,9,r["nombre_campo"]); ws.cell(i,10,r["fecha"])
    for col,w in zip("ABCDEFGHIJ",[14,28,10,10,14,14,14,12,20,12]):
        ws.column_dimensions[col].width=w
    return _excel_response(wb, f"tarjas_detalle_{fecha_inicio}_{fecha_termino}.xlsx")


@router.get("/api/tarjas/contratista/download-excel")
async def download_tarjas_contratista_excel(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    empresa: str = Query(None),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    if centro_costo: filters.append("cuartel_cc = %s"); params.append(centro_costo)
    if tipo_pago: filters.append("tipo_pago = %s"); params.append(tipo_pago)
    if labor: filters.append("labor = %s"); params.append(labor)
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, contratista, labor, tipo_pago, cuartel_cc, "
                f"total_trabajado, fecha::date::text AS fecha "
                f"FROM appsheet.tarjas_pagos {where} "
                "ORDER BY contratista, trabajador, fecha::date", params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Por contratista"
    _apply_header(ws, ["Trabajador","Contratista","Labor","Tipo de pago","CC","Total","Fecha"])
    money = '#,##0'
    for i,r in enumerate(rows,2):
        ws.cell(i,1,r["trabajador"]); ws.cell(i,2,r["contratista"]); ws.cell(i,3,r["labor"])
        ws.cell(i,4,r["tipo_pago"]); ws.cell(i,5,r["cuartel_cc"])
        c=ws.cell(i,6,float(r["total_trabajado"] or 0)); c.number_format=money
        ws.cell(i,7,r["fecha"])
    for col,w in zip("ABCDEFG",[28,24,28,16,12,14,12]):
        ws.column_dimensions[col].width=w
    return _excel_response(wb, f"tarjas_contratista_{fecha_inicio}_{fecha_termino}.xlsx")


@router.get("/api/tarjas/detalle-tractorista/download-excel")
async def download_tarjas_detalle_tractorista_excel(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    empresa: str = Query(None),
    centro_costo: str = Query(None),
    labor: str = Query(None),
    campo: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    filters = ["fecha BETWEEN %s AND %s", _TRACTORISTA_SQL]
    params: list = [fecha_inicio, fecha_termino]
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    if centro_costo: filters.append('"CC" = %s'); params.append(centro_costo)
    if labor: filters.append('"Nombre Labor" = %s'); params.append(labor)
    if campo: filters.append("nombre_campo = %s"); params.append(campo)
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT tipo_pago, "CC" AS centro_costo, "Nombre Labor" AS labor,
                       jornadas, total_unitario, total_labor AS costo_total,
                       contratista, nombre_campo, fecha::text AS fecha
                FROM appsheet.tarjas_reporte {where}
                ORDER BY contratista, "CC", "Nombre Labor"
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Detalle tractorista"
    _apply_header(ws, ["Tipo de pago","CC","Labor","Jornadas","Total unitario",
                        "Costo total","Contratista","Campo","Fecha"])
    money = '#,##0'
    for i,r in enumerate(rows,2):
        ws.cell(i,1,r["tipo_pago"]); ws.cell(i,2,r["centro_costo"]); ws.cell(i,3,r["labor"])
        ws.cell(i,4,r["jornadas"])
        c5=ws.cell(i,5,float(r["total_unitario"] or 0)); c5.number_format=money
        c6=ws.cell(i,6,float(r["costo_total"] or 0)); c6.number_format=money
        ws.cell(i,7,r["contratista"]); ws.cell(i,8,r["nombre_campo"]); ws.cell(i,9,r["fecha"])
    for col,w in zip("ABCDEFGHI",[14,10,28,10,14,14,24,20,12]):
        ws.column_dimensions[col].width=w
    return _excel_response(wb, f"tarjas_detalle_tractorista_{fecha_inicio}_{fecha_termino}.xlsx")


@router.get("/api/tarjas/general-tractorista/download-excel")
async def download_tarjas_general_tractorista_excel(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    centro_costo: str = Query(None),
    labor: str = Query(None),
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]
    if centro_costo: filters.append("cuartel_cc = %s"); params.append(centro_costo)
    if labor: filters.append("labor = %s"); params.append(labor)
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT trabajador, contratista, labor, tipo_pago,
                       ROUND(AVG(total_tractor)::numeric,2) AS promedio,
                       COALESCE(SUM(total_tractor),0) AS total
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista, labor, tipo_pago
                ORDER BY total DESC
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "General tractorista"
    _apply_header(ws, ["Trabajador","Contratista","Labor","Tipo de pago","Promedio","Total"])
    money = '#,##0'; money2 = '#,##0.00'
    for i,r in enumerate(rows,2):
        ws.cell(i,1,r["trabajador"]); ws.cell(i,2,r["contratista"])
        ws.cell(i,3,r["labor"]); ws.cell(i,4,r["tipo_pago"])
        c5=ws.cell(i,5,float(r["promedio"] or 0)); c5.number_format=money2
        c6=ws.cell(i,6,float(r["total"] or 0)); c6.number_format=money
    for col,w in zip("ABCDEF",[28,24,28,16,14,14]):
        ws.column_dimensions[col].width=w
    return _excel_response(wb, f"tarjas_general_tractorista_{fecha_inicio}_{fecha_termino}.xlsx")


@router.get("/api/tarjas/resumen-horas/download-excel")
async def download_tarjas_resumen_horas_excel(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    trabajador: str = Query(None),
    tipo_pago: str = Query(None),
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if trabajador: filters.append("trabajador = %s"); params.append(trabajador)
    if tipo_pago: filters.append("tipo_pago = %s"); params.append(tipo_pago)
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, contratista, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\\.[0-9]+)?$' "
                f"THEN horas_trabajadas::numeric ELSE 0 END),0)::int AS horas "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, contratista, tipo_pago, fecha::date "
                "ORDER BY trabajador, tipo_pago, fecha::date", params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    # Build pivot: worker → tipo_pago → date → hours
    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        key = (r["trabajador"] or "", r["contratista"] or "", r["tipo_pago"] or "")
        if key not in workers:
            workers[key] = {"by_date": {}, "total": 0}
        workers[key]["by_date"][r["fecha"]] = workers[key]["by_date"].get(r["fecha"],0) + (r["horas"] or 0)
        workers[key]["total"] += (r["horas"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Horas extra"
    headers = ["Trabajador","Contratista","Tipo de pago"] + [
        datetime.date.fromisoformat(d).strftime("%-d %b %Y") for d in dates
    ] + ["Total"]
    _apply_header(ws, headers)
    from openpyxl.styles import PatternFill, Font
    total_fill = PatternFill("solid", fgColor="D6E4F0")
    for row_num, ((trab, cont, tipo), entry) in enumerate(sorted_workers, 2):
        ws.cell(row_num,1,trab); ws.cell(row_num,2,cont); ws.cell(row_num,3,tipo)
        for col,d in enumerate(dates,4):
            v=entry["by_date"].get(d,0); ws.cell(row_num,col,v if v else None)
        tc=ws.cell(row_num,4+len(dates),entry["total"]); tc.fill=total_fill; tc.font=Font(bold=True)
    ws.column_dimensions["A"].width=28; ws.column_dimensions["B"].width=24; ws.column_dimensions["C"].width=18
    for i in range(len(dates)+1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(4+i)].width=12
    return _excel_response(wb, f"tarjas_horas_{fecha_inicio}_{fecha_termino}.xlsx")


@router.get("/api/tarjas/resumen-persona-tractorista/download-excel")
async def download_tarjas_resumen_persona_tractorista_excel(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    trabajador: str = Query(None),
    tipo_pago: str = Query(None),
    contratista: str = Query(None),
    empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]
    if trabajador: filters.append("trabajador = %s"); params.append(trabajador)
    if tipo_pago: filters.append("tipo_pago = %s"); params.append(tipo_pago)
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, contratista, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(total_tractor),0) AS total_tractor "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, contratista, tipo_pago, fecha::date "
                "ORDER BY trabajador, tipo_pago, fecha::date", params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        key = (r["trabajador"] or "", r["contratista"] or "", r["tipo_pago"] or "")
        if key not in workers:
            workers[key] = {"by_date": {}, "total": 0}
        workers[key]["by_date"][r["fecha"]] = workers[key]["by_date"].get(r["fecha"],0) + float(r["total_tractor"] or 0)
        workers[key]["total"] += float(r["total_tractor"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Tractorista"
    headers = ["Trabajador","Contratista","Tipo de pago"] + [
        datetime.date.fromisoformat(d).strftime("%-d %b %Y") for d in dates
    ] + ["Total"]
    _apply_header(ws, headers)
    from openpyxl.styles import PatternFill, Font
    total_fill = PatternFill("solid", fgColor="D6E4F0"); money = '#,##0'
    for row_num, ((trab, cont, tipo), entry) in enumerate(sorted_workers, 2):
        ws.cell(row_num,1,trab); ws.cell(row_num,2,cont); ws.cell(row_num,3,tipo)
        for col,d in enumerate(dates,4):
            v=entry["by_date"].get(d,0)
            c=ws.cell(row_num,col,v if v else None)
            if v: c.number_format=money
        tc=ws.cell(row_num,4+len(dates),entry["total"]); tc.number_format=money
        tc.fill=total_fill; tc.font=Font(bold=True)
    ws.column_dimensions["A"].width=28; ws.column_dimensions["B"].width=24; ws.column_dimensions["C"].width=18
    for i in range(len(dates)+1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(4+i)].width=14
    return _excel_response(wb, f"tarjas_tractorista_{fecha_inicio}_{fecha_termino}.xlsx")


# ===========================================================================
# PDF download endpoints
# ===========================================================================

@router.get("/api/tarjas/resumen-persona/download-pdf")
async def download_tarjas_resumen_persona_pdf(
    fecha_inicio: str = Query(...), fecha_termino: str = Query(...),
    trabajador: str = Query(None), tipo_pago: str = Query(None),
    contratista: str = Query(None), empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión")
    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if trabajador: filters.append("trabajador = %s"); params.append(trabajador)
    if tipo_pago: filters.append("tipo_pago = %s"); params.append(tipo_pago)
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(total_trabajado),0) AS total "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, tipo_pago, fecha::date ORDER BY trabajador, tipo_pago, fecha::date",
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        k = (r["trabajador"] or "", r["tipo_pago"] or "")
        if k not in workers:
            workers[k] = {"by_date": {}, "total": 0}
        workers[k]["by_date"][r["fecha"]] = workers[k]["by_date"].get(r["fecha"], 0) + float(r["total"] or 0)
        workers[k]["total"] += float(r["total"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    fmtCLP = lambda v: f"${v:,.0f}".replace(",", ".")
    date_headers = "".join(f'<th class="num">{datetime.date.fromisoformat(d).strftime("%-d %b")}</th>' for d in dates)
    rows_html = ""
    prev = None
    for (trab, tipo), entry in sorted_workers:
        is_first = prev != trab
        prev = trab
        cls = "worker-first" if is_first else ""
        rows_html += f'<tr class="{cls}"><td>{"<b>" + trab + "</b>" if is_first else ""}</td><td>{tipo}</td>'
        for d in dates:
            v = entry["by_date"].get(d, 0)
            rows_html += f'<td class="num">{"" if not v else fmtCLP(v)}</td>'
        rows_html += f'<td class="total">{fmtCLP(entry["total"])}</td></tr>'

    header = _pdf_header("Detalle trabajador — Tarjas", fecha_inicio, fecha_termino,
                         {"Empresa": empresa, "Contratista": contratista, "Trabajador": trabajador, "Tipo de pago": tipo_pago})
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_PDF_CSS}</style></head><body>
    {header}
    <p class="section-title">Resumen por trabajador</p>
    <table><thead>
      <tr><th>Trabajador</th><th>Tipo de pago</th>{date_headers}<th class="num">Total</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    </body></html>"""
    return _render_pdf(html, f"resumen_persona_{fecha_inicio}_{fecha_termino}.pdf")


@router.get("/api/tarjas/general/download-pdf")
async def download_tarjas_general_pdf(
    fecha_inicio: str = Query(...), fecha_termino: str = Query(...),
    centro_costo: str = Query(None), tipo_pago: str = Query(None),
    labor: str = Query(None), contratista: str = Query(None), empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión")
    where, params = _build_pagos_where(
        fecha_inicio, fecha_termino, centro_costo, tipo_pago, labor,
        contratista=contratista, nombre_campo=_empresa_to_campo(empresa),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT trabajador, contratista, ROUND(AVG(total_trabajado)::numeric,0) AS promedio,
                       COALESCE(SUM(total_trabajado),0) AS total
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista ORDER BY total DESC
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    fmtCLP = lambda v: f"${float(v):,.0f}".replace(",", ".")
    rows_html = "".join(
        f'<tr><td>{r["trabajador"]}</td><td>{r["contratista"]}</td>'
        f'<td class="num">{fmtCLP(r["promedio"])}</td><td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in rows
    )
    header = _pdf_header("General — Tarjas", fecha_inicio, fecha_termino,
                         {"Empresa": empresa, "Contratista": contratista, "CC": centro_costo, "Tipo de pago": tipo_pago, "Labor": labor})
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_PDF_CSS}</style></head><body>
    {header}
    <p class="section-title">Ranking por persona</p>
    <table><thead>
      <tr><th>Trabajador</th><th>Contratista</th><th class="num">Promedio</th><th class="num">Total</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    </body></html>"""
    return _render_pdf(html, f"general_{fecha_inicio}_{fecha_termino}.pdf")


@router.get("/api/tarjas/detalle/download-pdf")
async def download_tarjas_detalle_pdf(
    fecha_inicio: str = Query(...), fecha_termino: str = Query(...),
    contratista: str = Query(None), centro_costo: str = Query(None),
    tipo_pago: str = Query(None), labor: str = Query(None),
    campo: str = Query(None), empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión")
    filters = ["fecha BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if centro_costo: filters.append('"CC" = %s'); params.append(centro_costo)
    if tipo_pago: filters.append("tipo_pago = %s"); params.append(tipo_pago)
    if labor: filters.append('"Nombre Labor" = %s'); params.append(labor)
    if campo: filters.append("nombre_campo = %s"); params.append(campo)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT tipo_pago, "CC" AS cc, "Nombre Labor" AS labor, jornadas,
                       total_unitario, total_labor AS total, contratista, nombre_campo, fecha::text AS fecha
                FROM appsheet.tarjas_reporte {where}
                ORDER BY tipo_pago DESC, "CC", "Nombre Labor"
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    fmtCLP = lambda v: f"${float(v):,.0f}".replace(",", ".") if v else "—"
    rows_html = "".join(
        f'<tr><td>{r["tipo_pago"]}</td><td>{r["cc"]}</td><td>{r["labor"]}</td>'
        f'<td>{r["contratista"]}</td><td>{r["nombre_campo"]}</td><td class="num">{r["jornadas"]}</td>'
        f'<td class="num">{fmtCLP(r["total_unitario"])}</td><td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in rows
    )
    header = _pdf_header("Detalle de la semana — Tarjas", fecha_inicio, fecha_termino,
                         {"Empresa": empresa, "Contratista": contratista, "CC": centro_costo, "Tipo de pago": tipo_pago, "Labor": labor})
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_PDF_CSS}</style></head><body>
    {header}
    <table><thead>
      <tr><th>Tipo pago</th><th>CC</th><th>Labor</th><th>Contratista</th><th>Campo</th>
      <th class="num">Jornadas</th><th class="num">Unitario</th><th class="num">Total</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    </body></html>"""
    return _render_pdf(html, f"detalle_{fecha_inicio}_{fecha_termino}.pdf")


@router.get("/api/tarjas/contratista/download-pdf")
async def download_tarjas_contratista_pdf(
    fecha_inicio: str = Query(...), fecha_termino: str = Query(...),
    contratista: str = Query(None), centro_costo: str = Query(None),
    tipo_pago: str = Query(None), labor: str = Query(None), empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión")
    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if centro_costo: filters.append("cuartel_cc = %s"); params.append(centro_costo)
    if tipo_pago: filters.append("tipo_pago = %s"); params.append(tipo_pago)
    if labor: filters.append("labor = %s"); params.append(labor)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT trabajador, contratista, labor, tipo_pago,
                       COALESCE(SUM(total_trabajado),0) AS total, fecha::date::text AS fecha
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista, labor, tipo_pago, fecha::date
                ORDER BY contratista, trabajador, fecha::date
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    fmtCLP = lambda v: f"${float(v):,.0f}".replace(",", ".")
    rows_html = "".join(
        f'<tr><td>{r["trabajador"]}</td><td>{r["contratista"]}</td><td>{r["labor"]}</td>'
        f'<td>{r["tipo_pago"]}</td><td>{r["fecha"]}</td><td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in rows
    )
    header = _pdf_header("Detalle contratista — Tarjas", fecha_inicio, fecha_termino,
                         {"Empresa": empresa, "Contratista": contratista, "CC": centro_costo, "Tipo de pago": tipo_pago, "Labor": labor})
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_PDF_CSS}</style></head><body>
    {header}
    <table><thead>
      <tr><th>Trabajador</th><th>Contratista</th><th>Labor</th><th>Tipo de pago</th><th>Fecha</th><th class="num">Total</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    </body></html>"""
    return _render_pdf(html, f"contratista_{fecha_inicio}_{fecha_termino}.pdf")


@router.get("/api/tarjas/resumen-horas/download-pdf")
async def download_tarjas_resumen_horas_pdf(
    fecha_inicio: str = Query(...), fecha_termino: str = Query(...),
    trabajador: str = Query(None), tipo_pago: str = Query(None),
    contratista: str = Query(None), empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión")
    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if trabajador: filters.append("trabajador = %s"); params.append(trabajador)
    if tipo_pago: filters.append("tipo_pago = %s"); params.append(tipo_pago)
    if contratista: filters.append("contratista = %s"); params.append(contratista)
    if empresa: filters.append("nombre_campo = %s"); params.append(_empresa_to_campo(empresa))
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\\.[0-9]+)?$' "
                f"THEN horas_trabajadas::numeric ELSE 0 END),0)::int AS horas "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, tipo_pago, fecha::date ORDER BY trabajador, tipo_pago, fecha::date",
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        k = (r["trabajador"] or "", r["tipo_pago"] or "")
        if k not in workers:
            workers[k] = {"by_date": {}, "total": 0}
        workers[k]["by_date"][r["fecha"]] = workers[k]["by_date"].get(r["fecha"], 0) + (r["horas"] or 0)
        workers[k]["total"] += (r["horas"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    date_headers = "".join(f'<th class="num">{datetime.date.fromisoformat(d).strftime("%-d %b")}</th>' for d in dates)
    rows_html = ""
    prev = None
    for (trab, tipo), entry in sorted_workers:
        is_first = prev != trab
        prev = trab
        cls = "worker-first" if is_first else ""
        rows_html += f'<tr class="{cls}"><td>{"<b>" + trab + "</b>" if is_first else ""}</td><td>{tipo}</td>'
        for d in dates:
            v = entry["by_date"].get(d, 0)
            rows_html += f'<td class="num">{v if v else ""}</td>'
        rows_html += f'<td class="total">{entry["total"]}</td></tr>'

    header = _pdf_header("Horas extra por trabajador — Tarjas", fecha_inicio, fecha_termino,
                         {"Empresa": empresa, "Contratista": contratista, "Trabajador": trabajador, "Tipo de pago": tipo_pago})
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_PDF_CSS}</style></head><body>
    {header}
    <table><thead>
      <tr><th>Trabajador</th><th>Tipo de pago</th>{date_headers}<th class="num">Total hrs</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    </body></html>"""
    return _render_pdf(html, f"horas_{fecha_inicio}_{fecha_termino}.pdf")


# ===========================================================================
# Notas de crédito — contractor payment report (moved from despacho)
# ===========================================================================

@router.get("/tarjas/notas", response_class=HTMLResponse)
async def tarjas_notas_page(request: Request):
    return _templates.TemplateResponse(request, "despacho_notas.html")


@router.get("/api/tarjas/notas/filters")
async def get_tarjas_notas_filters():
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT nombre_campo FROM appsheet.tarjas_pagos "
                "WHERE nombre_campo IS NOT NULL AND estado = 'Aprobado' ORDER BY nombre_campo"
            )
            campos = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT contratista FROM appsheet.tarjas_pagos "
                "WHERE contratista IS NOT NULL AND estado = 'Aprobado' ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {"campos": campos, "contratistas": contratistas}


@router.get("/api/tarjas/notas")
async def get_tarjas_notas(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    campo: str = Query(None),
    contratista: str = Query(...),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["fecha::date BETWEEN %s AND %s", "contratista = %s", "estado = 'Aprobado'"]
    params: list = [fecha_inicio, fecha_termino, contratista]

    if campo:
        filters.append("nombre_campo = %s")
        params.append(campo)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    tipo_pago,
                    cuartel_cc              AS cc,
                    labor,
                    COUNT(*)                AS jornadas,
                    ROUND(
                      CASE
                        WHEN LOWER(TRIM(tipo_pago)) IN ('a trato', 'trato')
                          THEN AVG(NULLIF(total_trato, 0))
                        ELSE AVG(NULLIF(total_jornada, 0))
                      END::numeric, 0
                    )                       AS total_unitario,
                    COALESCE(SUM(total_pagar), 0) AS total_pagar
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY tipo_pago, cuartel_cc, labor
                ORDER BY
                    CASE WHEN LOWER(TRIM(tipo_pago)) IN ('a trato','trato') THEN 0 ELSE 1 END,
                    cuartel_cc, labor
            """, params)
            rows = _rows_to_dicts(cur)

            cur.execute(f"""
                SELECT
                    tipo_pago,
                    COALESCE(SUM(total_pagar), 0) AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY tipo_pago
            """, params)
            totals_by_tipo = {r[0]: float(r[1]) for r in cur.fetchall()}

            cur.execute(f"""
                SELECT DISTINCT nombre_campo
                FROM appsheet.tarjas_pagos
                {where}
                LIMIT 1
            """, params)
            row = cur.fetchone()
            nombre_campo = row[0] if row else ""

    finally:
        conn.close()

    total_trato = sum(
        r["total_pagar"] for r in rows
        if r["tipo_pago"] and r["tipo_pago"].lower().strip() in ("a trato", "trato")
    )
    total_aldia = sum(
        r["total_pagar"] for r in rows
        if r["tipo_pago"] and r["tipo_pago"].lower().strip() not in ("a trato", "trato")
    )
    total_general = total_trato + total_aldia

    return {
        "nombre_campo": nombre_campo,
        "contratista": contratista,
        "fecha_inicio": fecha_inicio,
        "fecha_termino": fecha_termino,
        "total_trato": total_trato,
        "total_aldia": total_aldia,
        "total_general": total_general,
        "rows": rows,
        "count": len(rows),
    }


@router.get("/api/tarjas/notas/odoo-export")
async def export_tarjas_notas_odoo(
    contratista: str = Query(...),
    campo: str = Query(...),
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    "Vendedor",
                    "Lineas del pedido/Producto/Nombre",
                    "Lineas del pedido/Cantidad",
                    "Lineas del pedido/Código de Distribución Analítica/Código",
                    "Lineas del pedido/Precio un.",
                    "partner_id",
                    "order_line/product_id",
                    "order_line/product_qty",
                    "order_line/analytic_distribution",
                    "order_line/price_unit"
                FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor"     = %s
                  AND "nombre_campo" = %s
                  AND "fecha" BETWEEN %s AND %s
                ORDER BY "fecha",
                         "Lineas del pedido/Código de Distribución Analítica/Código",
                         "Lineas del pedido/Producto/Nombre"
            """, (contratista, campo, fecha_inicio, fecha_termino))
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([str(v) if v is not None else "" for v in row])

    filename = (
        f"odoo_nota_{contratista.replace(' ', '_')}_{campo.replace(' ', '_')}"
        f"_{fecha_inicio}_{fecha_termino}.csv"
    )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
