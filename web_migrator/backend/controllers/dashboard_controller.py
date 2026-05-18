"""
controllers/dashboard_controller.py
------------------------------------
HTTP layer for the Dashboard page.

Routes:
  GET  /                    → Dashboard UI
  GET  /api/dashboard       → Aggregated metrics for all modules
"""

import datetime
import decimal
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth import require_auth
from db import get_connection

logger = logging.getLogger("controllers.dashboard")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None


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


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return _templates.TemplateResponse(request, "dashboard.html")


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/api/dashboard")
async def get_dashboard_data(
    fecha_inicio: str = Query(None),
    fecha_termino: str = Query(None),
):
    """Single endpoint that returns all dashboard metrics for a date range."""
    if fecha_inicio and not _DATE_RE.match(fecha_inicio):
        raise HTTPException(status_code=400, detail="fecha_inicio must be YYYY-MM-DD")
    if fecha_termino and not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="fecha_termino must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    data = {}
    try:
        with conn.cursor() as cur:
            # Build date WHERE clause
            if fecha_inicio and fecha_termino:
                date_filter = "fecha BETWEEN %s AND %s"
                date_params = [fecha_inicio, fecha_termino]
            else:
                date_filter = "fecha >= date_trunc('month', CURRENT_DATE) AND fecha < date_trunc('month', CURRENT_DATE) + interval '1 month'"
                date_params = []

            # ── Tarjas summary for selected range ─────────────────────
            cur.execute(f"""
                SELECT
                    COUNT(DISTINCT contratista)                      AS contratistas_activos,
                    COUNT(DISTINCT nombre_campo)                     AS campos_activos,
                    COUNT(DISTINCT "Nombre Labor")                   AS labores_distintas,
                    COALESCE(SUM(total_labor), 0)                    AS total_periodo,
                    COALESCE(SUM(CASE WHEN tipo_pago = 'trato'
                        THEN total_labor ELSE 0 END), 0)            AS total_trato,
                    COALESCE(SUM(CASE WHEN tipo_pago IN ('Al dia', 'Al día')
                        THEN total_labor ELSE 0 END), 0)            AS total_al_dia,
                    COALESCE(SUM(jornadas), 0)                       AS jornadas_periodo
                FROM appsheet.tarjas_reporte
                WHERE {date_filter}
            """, date_params)
            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
            data["tarjas_period"] = {k: _serialize(v) for k, v in zip(cols, row)}

            # ── Previous equivalent period (for comparison) ───────────
            if fecha_inicio and fecha_termino:
                d0 = datetime.date.fromisoformat(fecha_inicio)
                d1 = datetime.date.fromisoformat(fecha_termino)
                span = (d1 - d0).days + 1
                prev_end = d0 - datetime.timedelta(days=1)
                prev_start = prev_end - datetime.timedelta(days=span - 1)
                prev_filter = "fecha BETWEEN %s AND %s"
                prev_params = [str(prev_start), str(prev_end)]
            else:
                prev_filter = "fecha >= date_trunc('month', CURRENT_DATE) - interval '1 month' AND fecha < date_trunc('month', CURRENT_DATE)"
                prev_params = []

            cur.execute(f"""
                SELECT COALESCE(SUM(total_labor), 0) AS total_anterior
                FROM appsheet.tarjas_reporte
                WHERE {prev_filter}
            """, prev_params)
            data["tarjas_period"]["total_anterior"] = _serialize(cur.fetchone()[0])

            # ── Tarjas: daily totals within range ─────────────────────
            cur.execute(f"""
                SELECT
                    fecha::date AS dia,
                    COALESCE(SUM(total_labor), 0) AS total
                FROM appsheet.tarjas_reporte
                WHERE {date_filter}
                GROUP BY fecha::date
                ORDER BY dia
            """, date_params)
            data["tarjas_daily"] = _rows_to_dicts(cur)

            # ── Tarjas: top 5 contractors in range ────────────────────
            cur.execute(f"""
                SELECT
                    contratista,
                    COALESCE(SUM(total_labor), 0) AS total
                FROM appsheet.tarjas_reporte
                WHERE {date_filter}
                GROUP BY contratista
                ORDER BY total DESC
                LIMIT 5
            """, date_params)
            data["top_contratistas"] = _rows_to_dicts(cur)

            # ── Tarjas: top 5 labores in range ────────────────────────
            cur.execute(f"""
                SELECT
                    "Nombre Labor" AS labor,
                    COALESCE(SUM(jornadas), 0) AS jornadas,
                    COALESCE(SUM(total_labor), 0) AS total
                FROM appsheet.tarjas_reporte
                WHERE {date_filter}
                GROUP BY "Nombre Labor"
                ORDER BY jornadas DESC
                LIMIT 5
            """, date_params)
            data["top_labores"] = _rows_to_dicts(cur)

            # ── Sensors summary ───────────────────────────────────────
            cur.execute("""
                SELECT
                    COUNT(*)                                    AS total,
                    COUNT(*) FILTER (WHERE status = 'ok')      AS online,
                    COUNT(*) FILTER (WHERE status = 'offline') AS offline,
                    COUNT(DISTINCT field)                       AS campos
                FROM public.sensor_inventory
            """)
            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
            data["sensors"] = {k: _serialize(v) for k, v in zip(cols, row)}

            # ── Sensors by source ─────────────────────────────────────
            cur.execute("""
                SELECT
                    source,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'ok') AS online
                FROM public.sensor_inventory
                GROUP BY source
                ORDER BY source
            """)
            data["sensors_by_source"] = _rows_to_dicts(cur)

            # ── Recent alerts (offline sensors) ───────────────────────
            cur.execute("""
                SELECT
                    source, field, sensor_name, last_seen
                FROM public.sensor_inventory
                WHERE status = 'offline'
                ORDER BY last_seen DESC NULLS LAST
                LIMIT 5
            """)
            data["sensor_alerts"] = _rows_to_dicts(cur)

    finally:
        conn.close()

    return data
