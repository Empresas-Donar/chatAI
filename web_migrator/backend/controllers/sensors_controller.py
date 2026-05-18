"""
controllers/sensors_controller.py
----------------------------------
HTTP layer for the Sensors feature.

Routes:
  GET  /sensors                        → Sensor inventory UI page
  GET  /sensors/status                 → Daily system status UI page
  GET  /api/sensors/inventory          → Inventory data (filterable by source, field, status)
  GET  /api/sensors/inventory/summary  → Counts per source/status for the overview cards
  GET  /api/sensors/status             → Daily status records (last N days, filterable by field)
"""

import datetime
import decimal
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth import require_auth
from db import get_connection

logger = logging.getLogger("controllers.sensors")

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


def _row_to_dict(columns, row):
    return {k: _serialize(v) for k, v in zip(columns, row)}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/sensors", response_class=HTMLResponse)
async def sensor_inventory_page(request: Request):
    return _templates.TemplateResponse(request, "sensor_inventory.html")


@router.get("/sensors/status", response_class=HTMLResponse)
async def sensor_status_page(request: Request):
    return _templates.TemplateResponse(request, "sensor_status.html")


# ---------------------------------------------------------------------------
# API — Inventory
# ---------------------------------------------------------------------------

@router.get("/api/sensors/inventory/summary")
async def get_inventory_summary():
    """Cards: total, ok, offline broken down by source."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    source,
                    COUNT(*)                                        AS total,
                    COUNT(*) FILTER (WHERE status = 'ok')          AS ok,
                    COUNT(*) FILTER (WHERE status = 'offline')     AS offline,
                    COUNT(DISTINCT field)                           AS fields,
                    MAX(last_seen)                                  AS last_seen
                FROM public.sensor_inventory
                GROUP BY source
                ORDER BY source
            """)
            cols = [d[0] for d in cur.description]
            rows = [_row_to_dict(cols, r) for r in cur.fetchall()]

            # Overall totals
            cur.execute("""
                SELECT
                    COUNT(*)                                    AS total,
                    COUNT(*) FILTER (WHERE status = 'ok')      AS ok,
                    COUNT(*) FILTER (WHERE status = 'offline') AS offline
                FROM public.sensor_inventory
            """)
            totals_cols = [d[0] for d in cur.description]
            totals = _row_to_dict(totals_cols, cur.fetchone())
    finally:
        conn.close()

    return {"by_source": rows, "totals": totals}


@router.get("/api/sensors/inventory")
async def get_inventory(
    source: str = Query(None),
    field: str = Query(None),
    status: str = Query(None),
):
    """Return sensor inventory rows, optionally filtered."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = []
    params = []
    if source:
        filters.append("source = %s")
        params.append(source)
    if field:
        filters.append("field = %s")
        params.append(field)
    if status:
        filters.append("status = %s")
        params.append(status)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    id, source, field, zone, sensor_id, sensor_name,
                    unit, last_value, last_seen, status, updated_at
                FROM public.sensor_inventory
                {where}
                ORDER BY source, field, zone, sensor_name
            """, params)
            cols = [d[0] for d in cur.description]
            rows = [_row_to_dict(cols, r) for r in cur.fetchall()]
    finally:
        conn.close()

    return {"rows": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# API — System Status
# ---------------------------------------------------------------------------

@router.get("/api/sensors/status")
async def get_system_status(
    field: str = Query(None),
    days: int = Query(30, ge=1, le=365),
):
    """Return the last `days` of daily status records, optionally filtered by field."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["date >= CURRENT_DATE - %s::int"]
    params: list = [days]
    if field:
        filters.append("field = %s")
        params.append(field)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    id, date, field, status,
                    wc_executions, ubibot_channels,
                    temp_avg, temp_min, temp_max,
                    irrigation_mm, notes, updated_at
                FROM public.status_system
                {where}
                ORDER BY date DESC, field
            """, params)
            cols = [d[0] for d in cur.description]
            rows = [_row_to_dict(cols, r) for r in cur.fetchall()]

            # Distinct fields for filter dropdown
            cur.execute("SELECT DISTINCT field FROM public.status_system ORDER BY field")
            fields = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {"rows": rows, "fields": fields, "count": len(rows)}
