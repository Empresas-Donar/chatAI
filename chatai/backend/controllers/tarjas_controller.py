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

import base64
import datetime
import decimal
import io
from pathlib import Path
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


def _fmt_clp(v) -> str:
    try:
        return f"${int(float(v or 0)):,}".replace(",", ".")
    except Exception:
        return "-"


def _fmt_date_display(iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(iso)
        months = [
            "ene",
            "feb",
            "mar",
            "abr",
            "may",
            "jun",
            "jul",
            "ago",
            "sep",
            "oct",
            "nov",
            "dic",
        ]
        return f"{d.day} {months[d.month - 1]} {d.year}"
    except Exception:
        return iso


def _empresa_to_campo(empresa: str | None) -> str | None:
    return empresa or None


def _get_empresas(
    cur, table: str = "appsheet.tarjas_pagos", extra_where: str = ""
) -> list[str]:
    """Return distinct nombre_campo values as empresa options."""
    where = f"WHERE nombre_campo IS NOT NULL {('AND ' + extra_where) if extra_where else ''}"
    cur.execute(
        f"SELECT DISTINCT nombre_campo FROM {table} {where} ORDER BY nombre_campo"
    )
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


def _logo_b64() -> str:
    """Return the Donar logo as a base64-encoded PNG, resized to max 200 px wide.

    The original PNG is 1288×539 px (~680 KB, ~907 KB base64). Embedding that
    full size into the HTML string fed to xhtml2pdf causes text-layout corruption
    in table cells (issue #12). Resizing to ≤200 px wide brings the base64 to
    ~29 KB, which xhtml2pdf handles correctly.
    """
    path = (
        Path(__file__).parent.parent.parent
        / "frontend"
        / "static"
        / "img"
        / "donar_logo.png"
    )
    try:
        from PIL import Image

        img = Image.open(path)
        max_w = 200
        w, h = img.size
        if w > max_w:
            img = img.resize((max_w, int(h * max_w / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


_PDF_CSS = """
@page { size: A4 landscape; margin: 12mm 10mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 8pt; color: #111111; margin: 0; }
.ph { border-bottom: 1px solid #cccccc; padding: 6px 0 8px 0; margin-bottom: 6px; }
.ph h1 { font-size: 12pt; font-weight: bold; color: #111111; margin: 0 0 2px 0; }
.ph-sub { font-size: 7pt; color: #555555; margin: 0; }
.ph-chips { padding: 4px 0; margin-bottom: 8px; }
.chip { display: inline-block; border: 1px solid #aaaaaa; border-radius: 2px; padding: 1px 6px; font-size: 7pt; color: #333333; margin: 2px 3px 2px 0; }
.chip b { color: #111111; }
table { width: 100%; border-collapse: collapse; font-size: 7.5pt; }
th { background: #eeeeee; color: #111111; padding: 5px 6px; text-align: left; border: 1px solid #aaaaaa; font-weight: bold; }
th.num { text-align: right; }
td { padding: 3px 6px; border: 1px solid #cccccc; vertical-align: middle; }
tr:nth-child(even) td { background: #f7f7f7; }
tr.worker-first td { border-top: 1.5px solid #888888; }
.num { text-align: right; }
.total { text-align: right; font-weight: bold; border-left: 1.5px solid #888888; }
.section-title { font-size: 9pt; font-weight: bold; margin: 12px 0 5px 0; color: #111111; }
"""


def _pdf_header(
    title: str, fecha_inicio: str, fecha_termino: str, filters: dict
) -> str:
    now = datetime.date.today().strftime("%-d de %B de %Y")
    chips = ""
    for k, v in filters.items():
        if v:
            chips += f'<span class="chip"><b>{k}:</b> {v}</span> '
    logo = _logo_b64()
    logo_cell = (
        (
            f'<td style="border:none;width:90px;padding:4px 8px;background:#1e293b;vertical-align:middle">'
            f'<img src="data:image/png;base64,{logo}" style="width:80px;height:auto" /></td>'
        )
        if logo
        else ""
    )
    return f"""
    <table style="width:100%;border:none;margin-bottom:6px">
      <tr>
        {logo_cell}
        <td style="border:none;padding:0 0 0 10px;vertical-align:middle">
          <div class="ph">
            <h1>{title}</h1>
            <p class="ph-sub">Generado el {now}</p>
          </div>
        </td>
      </tr>
    </table>
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    fecha_inicio,
    fecha_termino,
    centro_costo,
    tipo_pago,
    labor,
    alias="",
    contratista=None,
    nombre_campo=None,
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    where, params = _build_pagos_where(
        fecha_inicio,
        fecha_termino,
        centro_costo,
        tipo_pago,
        labor,
        contratista=contratista,
        nombre_campo=_empresa_to_campo(empresa),
    )

    try:
        with conn.cursor() as cur:
            _horas_expr = """
                NULLIF(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\.[0-9]+)?$'
                               THEN horas_trabajadas::numeric ELSE 0 END), 0)
            """
            _horas_sum = """
                COALESCE(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\.[0-9]+)?$'
                               THEN horas_trabajadas::numeric ELSE 0 END), 0)
            """
            # 1) Average earnings per labor
            cur.execute(
                f"""
                SELECT
                    labor,
                    ROUND(AVG(total_trabajado)::numeric, 0)                        AS promedio_diario,
                    ROUND(SUM(total_trabajado)::numeric / {_horas_expr}, 0)        AS ganancia_hora,
                    ROUND(({_horas_sum})::numeric, 1)                              AS total_horas,
                    COALESCE(SUM(total_trabajado), 0)                              AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY labor
                ORDER BY total DESC
            """,
                params,
            )
            labor_summary = _rows_to_dicts(cur)

            # 2) Person ranking (top 6 earners)
            cur.execute(
                f"""
                SELECT
                    trabajador,
                    contratista,
                    ROUND(AVG(total_trabajado)::numeric, 0)                        AS promedio_diario,
                    ROUND(SUM(total_trabajado)::numeric / {_horas_expr}, 0)        AS ganancia_hora,
                    ROUND(({_horas_sum})::numeric, 1)                              AS total_horas,
                    COALESCE(SUM(total_trabajado), 0)                              AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY trabajador, contratista
                ORDER BY total DESC
                LIMIT 6
            """,
                params,
            )
            person_ranking = _rows_to_dicts(cur)

            # 3) Daily average by labor × cuadrilla (top 6 workers)
            p_where, p_params = _build_pagos_where(
                fecha_inicio,
                fecha_termino,
                centro_costo,
                tipo_pago,
                labor,
                alias="p",
                contratista=contratista,
                nombre_campo=_empresa_to_campo(empresa),
            )
            cur.execute(
                f"""
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
            """,
                params + p_params,
            )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT contratista FROM appsheet.tarjas_reporte ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]

            cur.execute(
                'SELECT DISTINCT "CC" FROM appsheet.tarjas_reporte WHERE "CC" IS NOT NULL ORDER BY "CC"'
            )
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute(
                'SELECT DISTINCT "Nombre Labor" FROM appsheet.tarjas_reporte ORDER BY "Nombre Labor"'
            )
            labores = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT nombre_campo FROM appsheet.tarjas_reporte ORDER BY nombre_campo"
            )
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


def _build_detalle_filters(
    fecha_inicio,
    fecha_termino,
    contratista=None,
    empresa=None,
    centro_costo=None,
    tipo_pago=None,
    labor=None,
    campo=None,
):
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
    return "WHERE " + " AND ".join(filters), params


def _query_detalle_rows(cur, where, params):
    cur.execute(
        f"""
        SELECT
            tipo_pago,
            "Nombre Labor"                                            AS labor,
            "CC"                                                      AS centro_costo,
            SUM(jornadas)                                             AS jornadas,
            SUM(horas_trabajadas)                                     AS horas_trabajadas,
            CASE WHEN SUM(jornadas) > 0
                 THEN ROUND((SUM(total_labor) / SUM(jornadas))::numeric, 2)
                 ELSE NULL END                                        AS total_unitario,
            SUM(total_labor)                                          AS costo_total,
            CASE WHEN SUM(horas_trabajadas) > 0
                 THEN ROUND((SUM(total_labor) / SUM(horas_trabajadas))::numeric, 0)
                 ELSE NULL END                                        AS costo_hora,
            ROUND(
                SUM(total_labor)::numeric
                / NULLIF(SUM(SUM(total_labor)) OVER (PARTITION BY tipo_pago), 0) * 100,
                2
            )                                                         AS pct_pago,
            nombre_campo
        FROM appsheet.tarjas_reporte
        {where}
        GROUP BY tipo_pago, "Nombre Labor", "CC", nombre_campo
        ORDER BY tipo_pago DESC, "Nombre Labor", "CC"
    """,
        params,
    )
    return _rows_to_dicts(cur)


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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    where, params = _build_detalle_filters(
        fecha_inicio,
        fecha_termino,
        contratista,
        empresa,
        centro_costo,
        tipo_pago,
        labor,
        campo,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT tipo_pago,
                       COALESCE(SUM(total_labor), 0) AS total_pagar,
                       COALESCE(SUM(jornadas), 0)    AS jornadas
                FROM appsheet.tarjas_reporte {where}
                GROUP BY tipo_pago ORDER BY tipo_pago
            """,
                params,
            )
            resumen = _rows_to_dicts(cur)
            rows = _query_detalle_rows(cur, where, params)
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT contratista FROM appsheet.tarjas_reporte "
                f"WHERE {_TRACTORISTA_SQL} ORDER BY contratista"
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
                f"SELECT DISTINCT nombre_campo FROM appsheet.tarjas_reporte "
                f"WHERE {_TRACTORISTA_SQL} ORDER BY nombre_campo"
            )
            campos = [r[0] for r in cur.fetchall()]
            empresas = _get_empresas(
                cur,
                "appsheet.tarjas_reporte",
                extra_where="LOWER(TRIM(tipo_pago)) = 'tractorista'",
            )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
            cur.execute(
                f"""
                SELECT
                    tipo_pago,
                    contratista,
                    COALESCE(SUM(total_labor), 0) AS total_pagar,
                    COALESCE(SUM(jornadas), 0)    AS jornadas
                FROM appsheet.tarjas_reporte
                {where}
                GROUP BY tipo_pago, contratista
                ORDER BY contratista
            """,
                params,
            )
            resumen_contratista = _rows_to_dicts(cur)

            cur.execute(
                f"""
                SELECT
                    tipo_pago,
                    "CC"                  AS centro_costo,
                    "Nombre Labor"        AS labor,
                    SUM(jornadas)         AS jornadas,
                    CASE WHEN SUM(jornadas) > 0
                         THEN ROUND((SUM(total_labor) / SUM(jornadas))::numeric, 2)
                         ELSE NULL END    AS total_unitario,
                    SUM(total_labor)      AS costo_total,
                    contratista,
                    nombre_campo
                FROM appsheet.tarjas_reporte
                {where}
                GROUP BY tipo_pago, "CC", "Nombre Labor", contratista, nombre_campo
                ORDER BY contratista, "CC", "Nombre Labor"
            """,
                params,
            )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
    try:
        with conn.cursor() as cur:
            maq_col = _resolve_maquina_column(cur)
            base_where = f" FROM appsheet.tarjas_pagos WHERE {_TRACTORISTA_PAGOS_SQL} "

            cur.execute(
                "SELECT DISTINCT contratista "
                + base_where
                + "AND contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT cuartel_cc "
                + base_where
                + "AND cuartel_cc IS NOT NULL ORDER BY cuartel_cc"
            )
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT labor "
                + base_where
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
            empresas = _get_empresas(
                cur,
                "appsheet.tarjas_pagos",
                extra_where="LOWER(TRIM(tipo_pago)) = 'tractorista'",
            )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
        workers[key]["by_date"][r["fecha"]] = workers[key]["by_date"].get(
            r["fecha"], 0
        ) + float(r["total_trabajado"] or 0)
        workers[key]["total"] += float(r["total_trabajado"] or 0)

    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resumen por persona"

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF")
    total_fill = PatternFill("solid", fgColor="D6E4F0")
    money_fmt = "#,##0"

    # Header row
    headers = (
        ["Trabajador", "Contratista", "Tipo de pago"]
        + [datetime.date.fromisoformat(d).strftime("%d/%m/%Y") for d in dates]
        + ["Total"]
    )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trabajador, COALESCE(SUM(CASE WHEN horas_extras ~ '^[0-9]+(\\.[0-9]+)?$' "
                "THEN horas_extras::numeric ELSE 0 END), 0)::numeric AS total "
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
                f"COALESCE(SUM(CASE WHEN horas_extras ~ '^[0-9]+(\\.[0-9]+)?$' "
                f"THEN horas_extras::numeric ELSE 0 END), 0)::numeric AS horas_trabajadas "
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
    return _templates.TemplateResponse(
        request, "tarjas_resumen_persona_tractorista.html"
    )


@router.get("/api/tarjas/resumen-persona-tractorista/filters")
async def get_tarjas_resumen_persona_tractorista_filters():
    """Filter options for the tractorista worker pivot."""
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
            empresas = _get_empresas(
                cur,
                "appsheet.tarjas_pagos",
                extra_where="LOWER(TRIM(tipo_pago)) = 'tractorista'",
            )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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

            maq_select = (
                psql.SQL(", {col} AS maquina")
                .format(col=psql.Identifier(maq_col))
                .as_string(conn)
                if maq_col
                else ", NULL AS maquina"
            )

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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
    try:
        with conn.cursor() as cur:
            maq_col = _resolve_maquina_column(cur)
            base = f" FROM appsheet.tarjas_pagos WHERE {_TRACTORISTA_PAGOS_SQL} "

            cur.execute(
                "SELECT DISTINCT cuartel_cc "
                + base
                + "AND cuartel_cc IS NOT NULL ORDER BY cuartel_cc"
            )
            centros_costo = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT labor " + base + "AND labor IS NOT NULL ORDER BY labor"
            )
            labores = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT contratista "
                + base
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
            empresas = _get_empresas(
                cur,
                "appsheet.tarjas_pagos",
                extra_where="LOWER(TRIM(tipo_pago)) = 'tractorista'",
            )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
            cur.execute(
                f"""
                SELECT
                    labor,
                    ROUND(AVG(total_tractor)::numeric, 2) AS avg_rate,
                    COALESCE(SUM(total_tractor), 0)       AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY labor
                ORDER BY total DESC
            """,
                params,
            )
            labor_summary = _rows_to_dicts(cur)

            # 2) Person ranking
            cur.execute(
                f"""
                SELECT
                    trabajador,
                    contratista,
                    ROUND(AVG(total_tractor)::numeric, 2) AS avg_rate,
                    COALESCE(SUM(total_tractor), 0)       AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY trabajador, contratista
                ORDER BY total DESC
            """,
                params,
            )
            person_ranking = _rows_to_dicts(cur)

            # 3) Daily average by labor × worker (top 6)
            cur.execute(
                f"""
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
                  AND {_TRACTORISTA_PAGOS_SQL.replace("tipo_pago", "p.tipo_pago")}
                GROUP BY p.labor, p.trabajador
                ORDER BY p.labor, avg_daily DESC
            """,
                params + [fecha_inicio, fecha_termino],
            )
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
        c.fill = fill
        c.font = font
        c.alignment = align


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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
    where, params = _build_pagos_where(
        fecha_inicio,
        fecha_termino,
        centro_costo,
        tipo_pago,
        labor,
        contratista=contratista,
        nombre_campo=_empresa_to_campo(empresa),
    )
    try:
        _horas_expr = """
            NULLIF(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\.[0-9]+)?$'
                           THEN horas_trabajadas::numeric ELSE 0 END), 0)
        """
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT trabajador, contratista, labor, tipo_pago,
                       ROUND(AVG(total_trabajado)::numeric, 0)                  AS promedio_diario,
                       ROUND(SUM(total_trabajado)::numeric / {_horas_expr}, 0)  AS ganancia_hora,
                       ROUND(SUM(total_pagar)::numeric    / {_horas_expr}, 0)   AS costo_hora,
                       COALESCE(SUM(total_trabajado),0) AS total
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista, labor, tipo_pago
                ORDER BY total DESC
            """,
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "General"
    _apply_header(
        ws,
        [
            "Trabajador",
            "Contratista",
            "Labor",
            "Tipo de pago",
            "Promedio diario",
            "Ganancia por hora",
            "Costo por hora",
            "Total",
        ],
    )
    money = "#,##0"
    for i, r in enumerate(rows, 2):
        ws.cell(i, 1, r["trabajador"])
        ws.cell(i, 2, r["contratista"])
        ws.cell(i, 3, r["labor"])
        ws.cell(i, 4, r["tipo_pago"])
        c5 = ws.cell(i, 5, float(r["promedio_diario"] or 0))
        c5.number_format = money
        c6 = ws.cell(
            i,
            6,
            float(r["ganancia_hora"] or 0) if r["ganancia_hora"] is not None else None,
        )
        c6.number_format = money
        c7 = ws.cell(
            i, 7, float(r["costo_hora"] or 0) if r["costo_hora"] is not None else None
        )
        c7.number_format = money
        c8 = ws.cell(i, 8, float(r["total"] or 0))
        c8.number_format = money
    for col, w in zip("ABCDEFGH", [28, 24, 28, 16, 14, 14, 14, 14]):
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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
    where, params = _build_detalle_filters(
        fecha_inicio,
        fecha_termino,
        contratista,
        empresa,
        centro_costo,
        tipo_pago,
        labor,
        campo,
    )
    try:
        with conn.cursor() as cur:
            rows = _query_detalle_rows(cur, where, params)
    finally:
        conn.close()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Detalle"
    _apply_header(
        ws,
        [
            "Tipo de pago",
            "Labor",
            "CC",
            "Costo por hora",
            "Jornadas",
            "Total unitario",
            "Costo total",
            "% Tipo pago",
            "Campo",
        ],
    )
    money = "#,##0"
    for i, r in enumerate(rows, 2):
        ws.cell(i, 1, r["tipo_pago"])
        ws.cell(i, 2, r["labor"])
        ws.cell(i, 3, r["centro_costo"])
        c4 = ws.cell(
            i, 4, float(r["costo_hora"]) if r["costo_hora"] is not None else None
        )
        c4.number_format = money
        ws.cell(i, 5, r["jornadas"])
        c6 = ws.cell(i, 6, float(r["total_unitario"] or 0))
        c6.number_format = money
        c7 = ws.cell(i, 7, float(r["costo_total"] or 0))
        c7.number_format = money
        ws.cell(i, 8, float(r["pct_pago"] or 0))
        ws.cell(i, 9, r["nombre_campo"])
    for col, w in zip("ABCDEFGHI", [14, 28, 10, 14, 10, 14, 14, 12, 20]):
        ws.column_dimensions[col].width = w
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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    _horas_sum = """COALESCE(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\\.[0-9]+)?$'
                        THEN horas_trabajadas::numeric ELSE 0 END), 0)"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT trabajador, contratista, labor, tipo_pago,
                       fecha::date::text AS fecha,
                       COALESCE(SUM(total_trabajado), 0) AS total,
                       {_horas_sum} AS horas
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista, labor, tipo_pago, fecha::date
                ORDER BY contratista, trabajador, labor, fecha::date
                """,
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    # Build pivot in Python
    from collections import OrderedDict
    dates = sorted({r["fecha"] for r in rows})
    groups: dict = OrderedDict()
    for r in rows:
        key = (r["trabajador"], r["contratista"], r["labor"], r["tipo_pago"])
        if key not in groups:
            groups[key] = {"total_ganado": 0.0, "total_horas": 0.0, "by_date": {}}
        g = groups[key]
        g["total_ganado"] += float(r["total"] or 0)
        g["total_horas"] += float(r["horas"] or 0)
        g["by_date"][r["fecha"]] = float(r["total"] or 0)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Por contratista"
    fixed_headers = ["Trabajador", "Contratista", "Labor", "Tipo de pago", "Costo/hr"]
    date_headers = [d[5:] for d in dates]  # MM-DD
    _apply_header(ws, fixed_headers + date_headers + ["Total"])

    fill_hdr, font_hdr, align_hdr = _excel_header_style()
    total_col_idx = len(fixed_headers) + len(dates) + 1

    # Style total column header
    ws.cell(1, total_col_idx).fill = fill_hdr
    ws.cell(1, total_col_idx).font = font_hdr
    ws.cell(1, total_col_idx).alignment = align_hdr

    money = "#,##0"
    for i, ((trabajador, cont, lab, tipo), g) in enumerate(groups.items(), 2):
        costo_hora = round(g["total_ganado"] / g["total_horas"]) if g["total_horas"] > 0 else None
        ws.cell(i, 1, trabajador)
        ws.cell(i, 2, cont)
        ws.cell(i, 3, lab)
        ws.cell(i, 4, tipo)
        c = ws.cell(i, 5, costo_hora)
        if costo_hora is not None:
            c.number_format = money
        for j, d in enumerate(dates, 6):
            val = g["by_date"].get(d)
            if val:
                dc = ws.cell(i, j, val)
                dc.number_format = money
        tc = ws.cell(i, total_col_idx, g["total_ganado"])
        tc.number_format = money
        from openpyxl.styles import Font
        tc.font = Font(bold=True)

    fixed_widths = [28, 22, 28, 14, 12]
    date_widths = [10] * len(dates)
    for col_letter, w in zip(
        [chr(65 + i) for i in range(len(fixed_widths) + len(date_widths) + 1)],
        fixed_widths + date_widths + [12],
    ):
        ws.column_dimensions[col_letter].width = w

    return _excel_response(
        wb, f"tarjas_contratista_{fecha_inicio}_{fecha_termino}.xlsx"
    )


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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
            cur.execute(
                f"""
                SELECT tipo_pago, "CC" AS centro_costo, "Nombre Labor" AS labor,
                       SUM(jornadas) AS jornadas,
                       CASE WHEN SUM(jornadas) > 0
                            THEN ROUND((SUM(total_labor) / SUM(jornadas))::numeric, 2)
                            ELSE NULL END AS total_unitario,
                       SUM(total_labor) AS costo_total,
                       contratista, nombre_campo
                FROM appsheet.tarjas_reporte {where}
                GROUP BY tipo_pago, "CC", "Nombre Labor", contratista, nombre_campo
                ORDER BY contratista, "CC", "Nombre Labor"
            """,
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Detalle tractorista"
    _apply_header(
        ws,
        [
            "Tipo de pago",
            "CC",
            "Labor",
            "Jornadas",
            "Total unitario",
            "Costo total",
            "Contratista",
            "Campo",
        ],
    )
    money = "#,##0"
    for i, r in enumerate(rows, 2):
        ws.cell(i, 1, r["tipo_pago"])
        ws.cell(i, 2, r["centro_costo"])
        ws.cell(i, 3, r["labor"])
        ws.cell(i, 4, r["jornadas"])
        c5 = ws.cell(i, 5, float(r["total_unitario"] or 0))
        c5.number_format = money
        c6 = ws.cell(i, 6, float(r["costo_total"] or 0))
        c6.number_format = money
        ws.cell(i, 7, r["contratista"])
        ws.cell(i, 8, r["nombre_campo"])
    for col, w in zip("ABCDEFGH", [14, 10, 28, 10, 14, 14, 24, 20]):
        ws.column_dimensions[col].width = w
    return _excel_response(
        wb, f"tarjas_detalle_tractorista_{fecha_inicio}_{fecha_termino}.xlsx"
    )


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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT trabajador, contratista, labor, tipo_pago,
                       ROUND(AVG(total_tractor)::numeric,2) AS promedio,
                       COALESCE(SUM(total_tractor),0) AS total
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista, labor, tipo_pago
                ORDER BY total DESC
            """,
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "General tractorista"
    _apply_header(
        ws, ["Trabajador", "Contratista", "Labor", "Tipo de pago", "Promedio", "Total"]
    )
    money = "#,##0"
    money2 = "#,##0.00"
    for i, r in enumerate(rows, 2):
        ws.cell(i, 1, r["trabajador"])
        ws.cell(i, 2, r["contratista"])
        ws.cell(i, 3, r["labor"])
        ws.cell(i, 4, r["tipo_pago"])
        c5 = ws.cell(i, 5, float(r["promedio"] or 0))
        c5.number_format = money2
        c6 = ws.cell(i, 6, float(r["total"] or 0))
        c6.number_format = money
    for col, w in zip("ABCDEF", [28, 24, 28, 16, 14, 14]):
        ws.column_dimensions[col].width = w
    return _excel_response(
        wb, f"tarjas_general_tractorista_{fecha_inicio}_{fecha_termino}.xlsx"
    )


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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
                f"COALESCE(SUM(CASE WHEN horas_extras ~ '^[0-9]+(\\.[0-9]+)?$' "
                f"THEN horas_extras::numeric ELSE 0 END),0)::numeric AS horas "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, contratista, tipo_pago, fecha::date "
                "ORDER BY trabajador, tipo_pago, fecha::date",
                params,
            )
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
        workers[key]["by_date"][r["fecha"]] = workers[key]["by_date"].get(
            r["fecha"], 0
        ) + (r["horas"] or 0)
        workers[key]["total"] += r["horas"] or 0
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Horas extra"
    headers = (
        ["Trabajador", "Contratista", "Tipo de pago"]
        + [datetime.date.fromisoformat(d).strftime("%d/%m/%Y") for d in dates]
        + ["Total"]
    )
    _apply_header(ws, headers)
    from openpyxl.styles import PatternFill, Font

    total_fill = PatternFill("solid", fgColor="D6E4F0")
    for row_num, ((trab, cont, tipo), entry) in enumerate(sorted_workers, 2):
        ws.cell(row_num, 1, trab)
        ws.cell(row_num, 2, cont)
        ws.cell(row_num, 3, tipo)
        for col, d in enumerate(dates, 4):
            v = entry["by_date"].get(d, 0)
            ws.cell(row_num, col, v if v else None)
        tc = ws.cell(row_num, 4 + len(dates), entry["total"])
        tc.fill = total_fill
        tc.font = Font(bold=True)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 18
    for i in range(len(dates) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(4 + i)].width = 12
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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    where = "WHERE " + " AND ".join(filters)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT trabajador, contratista, tipo_pago, fecha::date::text AS fecha, "
                f"COALESCE(SUM(total_tractor),0) AS total_tractor "
                f"FROM appsheet.tarjas_pagos {where} "
                "GROUP BY trabajador, contratista, tipo_pago, fecha::date "
                "ORDER BY trabajador, tipo_pago, fecha::date",
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()
    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        key = (r["trabajador"] or "", r["contratista"] or "", r["tipo_pago"] or "")
        if key not in workers:
            workers[key] = {"by_date": {}, "total": 0}
        workers[key]["by_date"][r["fecha"]] = workers[key]["by_date"].get(
            r["fecha"], 0
        ) + float(r["total_tractor"] or 0)
        workers[key]["total"] += float(r["total_tractor"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tractorista"
    headers = (
        ["Trabajador", "Contratista", "Tipo de pago"]
        + [datetime.date.fromisoformat(d).strftime("%d/%m/%Y") for d in dates]
        + ["Total"]
    )
    _apply_header(ws, headers)
    from openpyxl.styles import PatternFill, Font

    total_fill = PatternFill("solid", fgColor="D6E4F0")
    money = "#,##0"
    for row_num, ((trab, cont, tipo), entry) in enumerate(sorted_workers, 2):
        ws.cell(row_num, 1, trab)
        ws.cell(row_num, 2, cont)
        ws.cell(row_num, 3, tipo)
        for col, d in enumerate(dates, 4):
            v = entry["by_date"].get(d, 0)
            c = ws.cell(row_num, col, v if v else None)
            if v:
                c.number_format = money
        tc = ws.cell(row_num, 4 + len(dates), entry["total"])
        tc.number_format = money
        tc.fill = total_fill
        tc.font = Font(bold=True)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 18
    for i in range(len(dates) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(4 + i)].width = 14
    return _excel_response(
        wb, f"tarjas_tractorista_{fecha_inicio}_{fecha_termino}.xlsx"
    )


# ===========================================================================
# PDF download endpoints
# ===========================================================================


@router.get("/api/tarjas/resumen-persona/download-pdf")
async def download_tarjas_resumen_persona_pdf(
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
        raise HTTPException(status_code=503, detail="Error de conexión")
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
        workers[k]["by_date"][r["fecha"]] = workers[k]["by_date"].get(
            r["fecha"], 0
        ) + float(r["total"] or 0)
        workers[k]["total"] += float(r["total"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    fmtCLP = lambda v: f"${v:,.0f}".replace(",", ".")

    # Flat list layout — xhtml2pdf cannot reliably render wide pivot tables.
    # Rows: Trabajador | Tipo de pago | Fecha | Monto
    rows_html = ""
    prev = None
    for (trab, tipo), entry in sorted_workers:
        day_rows = sorted(
            ((d, v) for d, v in entry["by_date"].items() if v), key=lambda x: x[0]
        )
        for i, (d, v) in enumerate(day_rows):
            is_first_row = i == 0
            is_new_worker = prev != trab and is_first_row
            if is_new_worker:
                prev = trab
            cls = "worker-first" if is_new_worker else ""
            fecha_fmt = datetime.date.fromisoformat(d).strftime("%d/%m/%Y")
            rows_html += (
                f'<tr class="{cls}">'
                f'<td>{"<b>" + trab + "</b>" if is_first_row else ""}</td>'
                f"<td>{tipo if is_first_row else ''}</td>"
                f"<td>{fecha_fmt}</td>"
                f'<td class="num">{fmtCLP(v)}</td>'
                f"</tr>"
            )
        # subtotal row per worker+tipo
        rows_html += (
            f'<tr style="background:#e8e8e8">'
            f"<td></td><td></td>"
            f'<td style="font-weight:bold;text-align:right">Subtotal</td>'
            f'<td class="total">{fmtCLP(entry["total"])}</td>'
            f"</tr>"
        )

    logo = _logo_b64()
    logo_html = f'<img src="data:image/png;base64,{logo}" style="width:80px;height:auto" />' if logo else ""
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#1e293b;margin-bottom:12px">
      <tr>
        <td style="padding:10px 16px">{logo_html}</td>
        <td style="padding:10px 16px;color:#ffffff">
          <b style="font-size:14pt">Resumen por trabajador</b><br/>
          <span style="font-size:9pt">Desde: {fecha_inicio} &nbsp; Hasta: {fecha_termino}</span>
        </td>
      </tr>
    </table>
    <table border="1" cellpadding="4" cellspacing="0">
      <thead><tr><th>Trabajador</th><th>Tipo de pago</th><th>Fecha</th><th>Monto</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    </body></html>"""
    return _render_pdf(html, f"resumen_persona_{fecha_inicio}_{fecha_termino}.pdf")


@router.get("/api/tarjas/general/download-pdf")
async def download_tarjas_general_pdf(
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
        raise HTTPException(status_code=503, detail="Error de conexión")
    where, params = _build_pagos_where(
        fecha_inicio,
        fecha_termino,
        centro_costo,
        tipo_pago,
        labor,
        contratista=contratista,
        nombre_campo=_empresa_to_campo(empresa),
    )
    _horas_expr = "NULLIF(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\.[0-9]+)?$' THEN horas_trabajadas::numeric ELSE 0 END), 0)"
    _horas_sum = "COALESCE(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\.[0-9]+)?$' THEN horas_trabajadas::numeric ELSE 0 END), 0)"
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT labor,
                       ROUND(AVG(total_trabajado)::numeric, 0)           AS promedio_diario,
                       ROUND(SUM(total_trabajado)::numeric / {_horas_expr}, 0) AS ganancia_hora,
                       ROUND(({_horas_sum})::numeric, 1)                 AS total_horas,
                       COALESCE(SUM(total_trabajado), 0)                 AS total
                FROM appsheet.tarjas_pagos {where}
                GROUP BY labor ORDER BY total DESC
            """,
                params,
            )
            labor_rows = _rows_to_dicts(cur)
            cur.execute(
                f"""
                SELECT trabajador, contratista,
                       ROUND(AVG(total_trabajado)::numeric, 0)           AS promedio_diario,
                       ROUND(SUM(total_trabajado)::numeric / {_horas_expr}, 0) AS ganancia_hora,
                       ROUND(({_horas_sum})::numeric, 1)                 AS total_horas,
                       COALESCE(SUM(total_trabajado), 0)                 AS total
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista ORDER BY total DESC
            """,
                params,
            )
            ranking_rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    fmtCLP = lambda v: f"${float(v):,.0f}".replace(",", ".") if v is not None else "—"
    fmtHrs = lambda v: f"{float(v):,.1f} h".replace(",", ".") if v else "—"

    labor_html = "".join(
        f"<tr><td>{r['labor']}</td>"
        f'<td class="num">{fmtCLP(r["promedio_diario"])}</td>'
        f'<td class="num">{fmtCLP(r["ganancia_hora"])}</td>'
        f'<td class="num">{fmtHrs(r["total_horas"])}</td>'
        f'<td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in labor_rows
    )
    ranking_html = "".join(
        f"<tr><td>{r['trabajador']}</td><td>{r['contratista']}</td>"
        f'<td class="num">{fmtCLP(r["promedio_diario"])}</td>'
        f'<td class="num">{fmtCLP(r["ganancia_hora"])}</td>'
        f'<td class="num">{fmtHrs(r["total_horas"])}</td>'
        f'<td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in ranking_rows
    )
    header = _pdf_header(
        "General — Tarjas",
        fecha_inicio,
        fecha_termino,
        {
            "Empresa": empresa,
            "Contratista": contratista,
            "CC": centro_costo,
            "Tipo de pago": tipo_pago,
            "Labor": labor,
        },
    )
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_PDF_CSS}</style></head><body>
    {header}
    <p class="section-title">Ganancia promedio por labor</p>
    <table><thead>
      <tr><th>Labor</th><th class="num">Promedio diario</th>
      <th class="num">Ganancia por hora</th><th class="num">Horas</th><th class="num">Total</th></tr>
    </thead><tbody>{labor_html}</tbody></table>
    <p class="section-title">Ranking por persona</p>
    <table><thead>
      <tr><th>Trabajador</th><th>Contratista</th><th class="num">Promedio diario</th>
      <th class="num">Ganancia por hora</th><th class="num">Horas</th><th class="num">Total</th></tr>
    </thead><tbody>{ranking_html}</tbody></table>
    </body></html>"""
    return _render_pdf(html, f"general_{fecha_inicio}_{fecha_termino}.pdf")


@router.get("/api/tarjas/detalle/download-pdf")
async def download_tarjas_detalle_pdf(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
    campo: str = Query(None),
    empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión")
    where, params = _build_detalle_filters(
        fecha_inicio,
        fecha_termino,
        contratista,
        empresa,
        centro_costo,
        tipo_pago,
        labor,
        campo,
    )
    try:
        with conn.cursor() as cur:
            rows = _query_detalle_rows(cur, where, params)
    finally:
        conn.close()

    fmtCLP = lambda v: f"${float(v):,.0f}".replace(",", ".") if v else "—"
    fmtPct = lambda v: f"{float(v):.2f} %" if v is not None else "—"
    fmtHrs = lambda v: f"{float(v):,.1f} h".replace(",", ".") if v else "—"
    rows_html = "".join(
        f"<tr><td>{r['tipo_pago']}</td><td>{r['labor']}</td><td>{r['centro_costo']}</td>"
        f'<td class="num">{fmtCLP(r["costo_hora"])}</td>'
        f'<td class="num">{r["jornadas"]}</td>'
        f'<td class="num">{fmtHrs(r["horas_trabajadas"])}</td>'
        f'<td class="num">{fmtCLP(r["total_unitario"])}</td>'
        f'<td class="total">{fmtCLP(r["costo_total"])}</td>'
        f'<td class="num">{fmtPct(r["pct_pago"])}</td></tr>'
        for r in rows
    )
    header = _pdf_header(
        "Detalle de la semana — Tarjas",
        fecha_inicio,
        fecha_termino,
        {
            "Empresa": empresa,
            "Contratista": contratista,
            "CC": centro_costo,
            "Tipo de pago": tipo_pago,
            "Labor": labor,
        },
    )
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_PDF_CSS}</style></head><body>
    {header}
    <table><thead>
      <tr><th>Tipo pago</th><th>Labor</th><th>CC</th>
      <th class="num">Costo/hora</th><th class="num">Jornadas</th>
      <th class="num">Horas</th><th class="num">Unitario</th>
      <th class="num">Total</th><th class="num">% pago</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    </body></html>"""
    return _render_pdf(html, f"detalle_{fecha_inicio}_{fecha_termino}.pdf")


@router.get("/api/tarjas/contratista/download-pdf")
async def download_tarjas_contratista_pdf(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    contratista: str = Query(None),
    centro_costo: str = Query(None),
    tipo_pago: str = Query(None),
    labor: str = Query(None),
    empresa: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión")
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
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(_empresa_to_campo(empresa))
    where = "WHERE " + " AND ".join(filters)
    _horas_sum = """COALESCE(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\\.[0-9]+)?$'
                        THEN horas_trabajadas::numeric ELSE 0 END), 0)"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT trabajador, contratista, labor, tipo_pago,
                       COALESCE(SUM(total_trabajado), 0)  AS total,
                       {_horas_sum}                        AS horas,
                       COUNT(DISTINCT fecha::date)         AS dias
                FROM appsheet.tarjas_pagos {where}
                GROUP BY trabajador, contratista, labor, tipo_pago
                ORDER BY contratista, trabajador, labor
                """,
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    def clp(v):
        return f"${float(v):,.0f}".replace(",", ".")

    rows_html = ""
    prev_worker = None
    prev_cont = None
    for r in rows:
        trabajador = r["trabajador"] or ""
        cont = r["contratista"] or ""
        is_new_worker = trabajador != prev_worker
        row_cls = "worker-first" if is_new_worker else ""
        worker_cell = trabajador if is_new_worker else ""
        cont_cell = cont if cont != prev_cont else ""
        prev_worker = trabajador
        prev_cont = cont
        total = float(r["total"] or 0)
        horas = float(r["horas"] or 0)
        dias = int(r["dias"] or 0)
        costo_hora = clp(round(total / horas)) if horas > 0 else "-"
        prom_dia = clp(round(total / dias)) if dias > 0 else "-"
        rows_html += (
            f"<tr class='{row_cls}'>"
            f"<td>{worker_cell}</td><td>{cont_cell}</td>"
            f"<td>{r['labor']}</td><td>{r['tipo_pago']}</td>"
            f"<td class='num'>{costo_hora}</td>"
            f"<td class='num'>{prom_dia}</td>"
            f"<td class='num'>{dias}</td>"
            f"<td class='total'>{clp(total)}</td></tr>"
        )

    header = _pdf_header(
        "Resumen por trabajador — Tarjas",
        fecha_inicio,
        fecha_termino,
        {
            "Empresa": empresa,
            "Contratista": contratista,
            "CC": centro_costo,
            "Tipo de pago": tipo_pago,
            "Labor": labor,
        },
    )
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_PDF_CSS}</style></head><body>
    {header}
    <table><thead>
      <tr>
        <th>Trabajador</th><th>Contratista</th><th>Labor</th>
        <th>Tipo</th>
        <th class="num">Costo/hr</th>
        <th class="num">Prom/día</th>
        <th class="num">Días</th>
        <th class="num">Total</th>
      </tr>
    </thead><tbody>{rows_html}</tbody></table>
    </body></html>"""
    return _render_pdf(html, f"contratista_{fecha_inicio}_{fecha_termino}.pdf")


@router.get("/api/tarjas/resumen-horas/download-pdf")
async def download_tarjas_resumen_horas_pdf(
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
        raise HTTPException(status_code=503, detail="Error de conexión")
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
                f"COALESCE(SUM(CASE WHEN horas_extras ~ '^[0-9]+(\\.[0-9]+)?$' "
                f"THEN horas_extras::numeric ELSE 0 END),0)::numeric AS horas "
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
        workers[k]["by_date"][r["fecha"]] = workers[k]["by_date"].get(r["fecha"], 0) + (
            r["horas"] or 0
        )
        workers[k]["total"] += r["horas"] or 0
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    date_headers = "".join(
        f'<th class="num">{datetime.date.fromisoformat(d).strftime("%d/%m")}</th>'
        for d in dates
    )
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

    header = _pdf_header(
        "Horas extra por trabajador — Tarjas",
        fecha_inicio,
        fecha_termino,
        {
            "Empresa": empresa,
            "Contratista": contratista,
            "Trabajador": trabajador,
            "Tipo de pago": tipo_pago,
        },
    )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    filters = [
        "fecha::date BETWEEN %s AND %s",
        "contratista = %s",
        "estado = 'Aprobado'",
    ]
    params: list = [fecha_inicio, fecha_termino, contratista]

    if campo:
        filters.append("nombre_campo = %s")
        params.append(campo)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
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
            """,
                params,
            )
            rows = _rows_to_dicts(cur)

            cur.execute(
                f"""
                SELECT
                    tipo_pago,
                    COALESCE(SUM(total_pagar), 0) AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY tipo_pago
            """,
                params,
            )
            totals_by_tipo = {r[0]: float(r[1]) for r in cur.fetchall()}

            cur.execute(
                f"""
                SELECT DISTINCT nombre_campo
                FROM appsheet.tarjas_pagos
                {where}
                LIMIT 1
            """,
                params,
            )
            row = cur.fetchone()
            nombre_campo = row[0] if row else ""

    finally:
        conn.close()

    total_trato = sum(
        r["total_pagar"]
        for r in rows
        if r["tipo_pago"] and r["tipo_pago"].lower().strip() in ("a trato", "trato")
    )
    total_aldia = sum(
        r["total_pagar"]
        for r in rows
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
    nc_total: int = Query(
        None, description="Monto total NC para redistribución proporcional"
    ),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    # Auto-sync unmapped labores (same as purchase orders export)
    from .purchase_orders_controller import _sync_labores

    try:
        _sync_labores(conn, fecha_inicio, fecha_termino, contratista, campo)
    except Exception as exc:
        logger.warning(f"Labor auto-sync failed (non-fatal): {exc}")

    excluded_amount = 0.0
    try:
        with conn.cursor() as cur:
            # Sum excluded rows (no product_id or unmapped CC)
            cur.execute(
                """
                SELECT COALESCE(SUM("order_line/product_qty" * "order_line/price_unit"), 0)
                FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor"     = %s
                  AND nombre_campo   = %s
                  AND fecha BETWEEN %s AND %s
                  AND (
                      "order_line/product_id" IS NULL
                      OR "order_line/analytic_distribution" LIKE '%%"": %%'
                  )
            """,
                (contratista, campo, fecha_inicio, fecha_termino),
            )
            excluded_amount = float(cur.fetchone()[0] or 0)

            # Group and aggregate valid rows — same structure as purchase orders
            cur.execute(
                """
                SELECT
                    "partner_id",
                    "order_line/product_id",
                    SUM("order_line/product_qty")               AS qty,
                    "order_line/analytic_distribution",
                    CASE WHEN SUM("order_line/product_qty") > 0
                         THEN ROUND(
                             SUM("order_line/product_qty" * "order_line/price_unit")
                             / SUM("order_line/product_qty"), 2)
                         ELSE NULL END                          AS price_unit
                FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor"      = %s
                  AND "nombre_campo"  = %s
                  AND "fecha" BETWEEN %s AND %s
                  AND "order_line/product_id" IS NOT NULL
                  AND "order_line/analytic_distribution" NOT LIKE '%%"": %%'
                GROUP BY
                    "partner_id",
                    "order_line/product_id",
                    "order_line/analytic_distribution"
                ORDER BY "order_line/product_id"
            """,
                (contratista, campo, fecha_inicio, fecha_termino),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    # If nc_total provided, scale price_unit proportionally
    if nc_total and nc_total > 0 and rows:
        original_total = sum(
            float(qty or 0) * float(price or 0) for _, _, qty, _, price in rows
        )
        scale = nc_total / original_total if original_total else 1.0
        rows = [
            (
                partner,
                product,
                qty,
                analytic,
                round(float(price) * scale, 2) if price is not None else None,
            )
            for partner, product, qty, analytic, price in rows
        ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"

    headers = [
        "partner_id",
        "order_line/product_id",
        "order_line/product_qty",
        "order_line/analytic_distribution",
        "order_line/price_unit",
    ]
    ws.append(headers)

    for i, (partner_id, product_id, qty, analytic, price) in enumerate(rows):
        ws.append(
            [
                partner_id if i == 0 else None,
                product_id,
                float(qty) if qty is not None else None,
                analytic,
                float(price) if price is not None else None,
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = (
        f"odoo_nota_{contratista.replace(' ', '_')}_{campo.replace(' ', '_')}"
        f"_{fecha_inicio}_{fecha_termino}.xlsx"
    )
    response_headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Access-Control-Expose-Headers": "X-Excluded-Amount",
    }
    if excluded_amount > 0:
        response_headers["X-Excluded-Amount"] = str(int(excluded_amount))

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=response_headers,
    )


# ---------------------------------------------------------------------------
# Nota de crédito print-PDF  (opens in new tab, same layout as the web page)
# ---------------------------------------------------------------------------

_NOTA_PDF_CSS = """
@page { size: A4 landscape; margin: 12mm 14mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 8pt; color: #111; margin: 0; }
.hdr-table { width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; margin-bottom: 10px; }
.hdr-logo  { width: 120px; padding: 8px 12px; vertical-align: middle; text-align: center;
             border-right: 1px solid #e2e8f0; background: #1e293b; }
.hdr-logo-img { width: 100px; height: auto; }
.hdr-mid   { padding: 10px 14px; vertical-align: top; }
.hdr-right { width: 190px; padding: 10px 14px; vertical-align: top; text-align: right;
             border-left: 1px solid #e2e8f0; }
.co-name   { font-size: 14pt; font-weight: 800; margin: 0 0 3px; }
.co-sub    { font-size: 9pt; font-weight: 600; margin: 0 0 2px; }
.co-week   { font-size: 7.5pt; color: #64748b; margin: 0; }
.dt-row    { margin-bottom: 5px; font-size: 8pt; }
.dt-label  { font-weight: 600; }
.dt-val    { background: #fef9c3; padding: 1px 7px; font-weight: 700; }
.grand-tot { font-size: 15pt; font-weight: 800; margin-top: 8px; }
.glosa-table { width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; margin-bottom: 10px; }
.glosa-title { background: #1e293b; color: white; text-align: center;
               padding: 6px; font-weight: 700; font-size: 8pt; letter-spacing: .5px; }
.glosa-body  { background: #fef08a; text-align: center; padding: 8px 12px;
               font-size: 8.5pt; font-weight: 700; color: #1e293b; }
.totals-row  { border-top: 2px solid #1e293b; }
.tot-cell    { text-align: center; padding: 8px 6px; width: 33%;
               border-right: 1px solid #e2e8f0; }
.tot-cell-hl { background: #fef08a; }
.tot-label   { font-size: 7pt; font-weight: 700; color: #64748b; text-transform: uppercase; }
.tot-value   { font-size: 13pt; font-weight: 800; color: #1e293b; margin-top: 2px; }
.detail-table { width: 100%; border-collapse: collapse; font-size: 7.5pt; margin-top: 8px; }
.detail-table thead tr { background: #1d4ed8; color: white; }
.detail-table thead th { padding: 6px 8px; text-align: left; font-weight: bold; }
.detail-table thead th.num { text-align: right; }
.detail-table tbody tr.even { background: #f8fafc; }
.detail-table tbody td { padding: 4px 8px; border-bottom: 1px solid #f1f5f9; }
.detail-table td.num { text-align: right; }
.badge-trato { color: #1d4ed8; font-weight: 700; }
.badge-aldia { color: #15803d; font-weight: 700; }
"""


@router.get("/api/tarjas/notas/print-pdf")
async def notas_print_pdf(
    contratista: str = Query(...),
    campo: str = Query(None),
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    nc_total: int = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    filters = [
        "fecha::date BETWEEN %s AND %s",
        "contratista = %s",
        "estado = 'Aprobado'",
    ]
    params: list = [fecha_inicio, fecha_termino, contratista]
    if campo:
        filters.append("nombre_campo = %s")
        params.append(campo)
    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT tipo_pago, cuartel_cc AS cc, labor,
                       COUNT(*) AS jornadas,
                       ROUND(CASE
                         WHEN LOWER(TRIM(tipo_pago)) IN ('a trato','trato')
                           THEN AVG(NULLIF(total_trato, 0))
                         ELSE AVG(NULLIF(total_jornada, 0))
                       END::numeric, 0) AS total_unitario,
                       COALESCE(SUM(total_pagar), 0) AS total_pagar
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY tipo_pago, cuartel_cc, labor
                ORDER BY
                    CASE WHEN LOWER(TRIM(tipo_pago)) IN ('a trato','trato') THEN 0 ELSE 1 END,
                    cuartel_cc, labor
            """,
                params,
            )
            rows = cur.fetchall()

            cur.execute(
                f"SELECT DISTINCT nombre_campo FROM appsheet.tarjas_pagos {where} LIMIT 1",
                params,
            )
            r = cur.fetchone()
            nombre_campo = r[0] if r else (campo or "")
    finally:
        conn.close()

    if not rows:
        raise HTTPException(
            status_code=404, detail="Sin datos para los filtros indicados"
        )

    total_general = sum(float(r[5] or 0) for r in rows)

    # Apply NC redistribution if requested (largest-remainder method)
    if nc_total and nc_total > 0 and total_general > 0:
        scale = nc_total / total_general
        exact = [float(r[5] or 0) * scale for r in rows]
        floored = [int(v) for v in exact]
        remainder = nc_total - sum(floored)
        fracs = sorted(range(len(exact)), key=lambda i: -(exact[i] - floored[i]))
        for i in range(remainder):
            floored[fracs[i]] += 1
        rows = [(*r[:5], floored[i]) for i, r in enumerate(rows)]
        total_general = nc_total

    total_trato = sum(
        float(r[5] or 0)
        for r in rows
        if (r[0] or "").lower().strip() in ("a trato", "trato")
    )
    total_aldia = total_general - total_trato

    d1 = _fmt_date_display(fecha_inicio)
    d2 = _fmt_date_display(fecha_termino)
    glosa = f"SERVICIOS DE LABORES AGRÍCOLAS {d1.upper()} AL {d2.upper()}"
    semana = f"Semana desde {d1} al {d2}"
    empresa_display = (
        f"AGRÍCOLA DONAR — {nombre_campo.upper()}" if nombre_campo else "AGRÍCOLA DONAR"
    )

    rows_html = ""
    for i, (tipo, cc, labor, jornadas, unitario, total) in enumerate(rows):
        is_trato = (tipo or "").lower().strip() in ("trato", "a trato")
        tipo_label = "Trato" if is_trato else "Al día"
        tipo_cls = "badge-trato" if is_trato else "badge-aldia"
        even_cls = "even" if i % 2 == 0 else ""
        rows_html += f"""<tr class="{even_cls}">
          <td><span class="{tipo_cls}">{tipo_label}</span></td>
          <td>{cc or ""}</td>
          <td>{labor or ""}</td>
          <td class="num">{int(jornadas) if jornadas is not None else "–"}</td>
          <td class="num">{_fmt_clp(unitario)}</td>
          <td class="num">{_fmt_clp(total)}</td>
        </tr>"""

    logo = _logo_b64()
    logo_html = (
        f'<img src="data:image/png;base64,{logo}" class="hdr-logo-img" />'
        if logo
        else "EMPRESAS DONAR"
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Nota de Crédito — {contratista}</title>
<style>{_NOTA_PDF_CSS}</style>
</head><body>

<table class="hdr-table">
  <tr>
    <td class="hdr-logo">{logo_html}</td>
    <td class="hdr-mid">
      <p class="co-name">{empresa_display}</p>
      <p class="co-sub">Contratista: {contratista}</p>
      <p class="co-week">{semana}</p>
    </td>
    <td class="hdr-right">
      <p class="dt-row"><span class="dt-label">Fecha Inicio&nbsp;&nbsp;</span>
        <span class="dt-val">{d1}</span></p>
      <p class="dt-row"><span class="dt-label">Fecha Término&nbsp;&nbsp;</span>
        <span class="dt-val">{d2}</span></p>
      <p class="grand-tot">{_fmt_clp(total_general)}</p>
    </td>
  </tr>
</table>

<table class="glosa-table">
  <tr><td colspan="3" class="glosa-title">GLOSA</td></tr>
  <tr><td colspan="3" class="glosa-body">{glosa}</td></tr>
  <tr class="totals-row">
    <td class="tot-cell"><div class="tot-label">Total a Trato</div>
      <div class="tot-value">{_fmt_clp(total_trato)}</div></td>
    <td class="tot-cell"><div class="tot-label">Total Al Día</div>
      <div class="tot-value">{_fmt_clp(total_aldia)}</div></td>
    <td class="tot-cell tot-cell-hl"><div class="tot-label">Total a Pagar</div>
      <div class="tot-value">{_fmt_clp(total_general)}</div></td>
  </tr>
</table>

<table class="detail-table">
  <thead>
    <tr>
      <th>Tipo de Pago</th><th>CC</th><th>Nombre Labor</th>
      <th class="num">Jornadas</th><th class="num">Precio Unitario</th>
      <th class="num">Total a Pagar</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>

</body></html>"""

    buf = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html), dest=buf)
    buf.seek(0)
    filename = (
        f"nota_{contratista.replace(' ', '_')}_{(campo or 'all').replace(' ', '_')}"
        f"_{fecha_inicio}_{fecha_termino}.pdf"
    )
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
