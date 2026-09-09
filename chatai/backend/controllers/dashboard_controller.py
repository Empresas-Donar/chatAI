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
from tarjas_empresa import fold_costo_empresa

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


def _pagos_date_sql(fecha_inicio, fecha_termino):
    if fecha_inicio and fecha_termino:
        return "fecha::date BETWEEN %s AND %s", [fecha_inicio, fecha_termino]
    return (
        "fecha::date >= date_trunc('month', CURRENT_DATE)::date "
        "AND fecha::date < (date_trunc('month', CURRENT_DATE) + interval '1 month')::date",
        [],
    )


def _fold_by_key(rows, key):
    """rows: (key, tipo_pago, total_trabajado, extra...). Return dict key -> costo."""
    grouped = {}
    extras = {}
    for r in rows:
        k, tipo, trab = r[0], r[1], r[2]
        grouped.setdefault(k, []).append((tipo, trab))
        if len(r) > 3:
            extras[k] = r[3]
    out = []
    for k, pairs in grouped.items():
        item = {key: k, "total": fold_costo_empresa(pairs)}
        if k in extras:
            item["jornadas"] = extras[k]
        out.append(item)
    return out


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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    data = {}
    try:
        with conn.cursor() as cur:
            date_filter, date_params = _pagos_date_sql(fecha_inicio, fecha_termino)
            pagos_scope = f"estado = 'Aprobado' AND {date_filter}"

            # ── Tarjas summary for selected range (Costo Empresa) ─────
            cur.execute(
                f"""
                SELECT
                    COUNT(DISTINCT contratista) AS contratistas_activos,
                    COUNT(DISTINCT nombre_campo) AS campos_activos,
                    COUNT(DISTINCT labor) AS labores_distintas,
                    COUNT(*) AS jornadas_periodo
                FROM appsheet.tarjas_pagos
                WHERE {pagos_scope}
                """,
                date_params,
            )
            counts = {k: _serialize(v) for k, v in zip(
                [d[0] for d in cur.description], cur.fetchone()
            )}
            cur.execute(
                f"""
                SELECT tipo_pago, COALESCE(SUM(total_trabajado), 0)
                FROM appsheet.tarjas_pagos
                WHERE {pagos_scope}
                GROUP BY tipo_pago
                """,
                date_params,
            )
            tipo_pairs = cur.fetchall()
            total_periodo = fold_costo_empresa(tipo_pairs)
            total_trato = fold_costo_empresa(
                [(t, a) for t, a in tipo_pairs if t == "trato"]
            )
            total_al_dia = total_periodo - total_trato
            data["tarjas_period"] = {
                **counts,
                "total_periodo": total_periodo,
                "total_trato": total_trato,
                "total_al_dia": total_al_dia,
            }

            # ── Previous equivalent period (for comparison) ───────────
            if fecha_inicio and fecha_termino:
                d0 = datetime.date.fromisoformat(fecha_inicio)
                d1 = datetime.date.fromisoformat(fecha_termino)
                span = (d1 - d0).days + 1
                prev_end = d0 - datetime.timedelta(days=1)
                prev_start = prev_end - datetime.timedelta(days=span - 1)
                prev_filter = "fecha::date BETWEEN %s AND %s"
                prev_params = [str(prev_start), str(prev_end)]
            else:
                prev_filter = (
                    "fecha::date >= (date_trunc('month', CURRENT_DATE) - interval '1 month')::date "
                    "AND fecha::date < date_trunc('month', CURRENT_DATE)::date"
                )
                prev_params = []

            cur.execute(
                f"""
                SELECT tipo_pago, COALESCE(SUM(total_trabajado), 0)
                FROM appsheet.tarjas_pagos
                WHERE estado = 'Aprobado' AND {prev_filter}
                GROUP BY tipo_pago
                """,
                prev_params,
            )
            data["tarjas_period"]["total_anterior"] = fold_costo_empresa(
                cur.fetchall()
            )

            # ── Tarjas: daily totals within range ─────────────────────
            cur.execute(
                f"""
                SELECT fecha::date AS dia, tipo_pago,
                       COALESCE(SUM(total_trabajado), 0)
                FROM appsheet.tarjas_pagos
                WHERE {pagos_scope}
                GROUP BY fecha::date, tipo_pago
                ORDER BY dia
                """,
                date_params,
            )
            by_day = {}
            for dia, tipo, trab in cur.fetchall():
                key = str(dia)
                by_day.setdefault(key, []).append((tipo, trab))
            data["tarjas_daily"] = [
                {"dia": dia, "total": fold_costo_empresa(pairs)}
                for dia, pairs in by_day.items()
            ]

            # ── Tarjas: top 5 contractors in range ────────────────────
            cur.execute(
                f"""
                SELECT contratista, tipo_pago, COALESCE(SUM(total_trabajado), 0)
                FROM appsheet.tarjas_pagos
                WHERE {pagos_scope}
                GROUP BY contratista, tipo_pago
                """,
                date_params,
            )
            contractors = _fold_by_key(cur.fetchall(), "contratista")
            contractors.sort(key=lambda r: r["total"], reverse=True)
            data["top_contratistas"] = contractors[:5]

            # ── Tarjas: top 5 labores in range ────────────────────────
            cur.execute(
                f"""
                SELECT labor, tipo_pago, COALESCE(SUM(total_trabajado), 0),
                       COUNT(*) AS jornadas
                FROM appsheet.tarjas_pagos
                WHERE {pagos_scope}
                GROUP BY labor, tipo_pago
                """,
                date_params,
            )
            labor_pairs = {}
            labor_jornadas = {}
            for labor, tipo, trab, jornadas in cur.fetchall():
                labor_pairs.setdefault(labor, []).append((tipo, trab))
                labor_jornadas[labor] = labor_jornadas.get(labor, 0) + int(jornadas or 0)
            labores = [
                {
                    "labor": labor,
                    "jornadas": labor_jornadas[labor],
                    "total": fold_costo_empresa(pairs),
                }
                for labor, pairs in labor_pairs.items()
            ]
            labores.sort(key=lambda r: r["jornadas"], reverse=True)
            data["top_labores"] = labores[:5]

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
