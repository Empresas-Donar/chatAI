"""
controllers/despacho_controller.py
-----------------------------------
HTTP layer for Despacho reports.

Routes:
  GET  /despacho/notas                  → Notas de crédito page
  GET  /api/despacho/notas/filters      → Filter options
  GET  /api/despacho/notas              → Report data

  GET  /despacho/odoo                   → Odoo export page
  GET  /api/despacho/odoo/filters       → Filter options (clientes, fechas)
  GET  /api/despacho/odoo/download      → CSV download for Odoo import
"""

import csv
import datetime
import decimal
import io
import json
import logging
import re
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from auth import require_auth
from db import get_connection

logger = logging.getLogger("controllers.despacho")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
# Notas de crédito — contractor payment report
# ===========================================================================

@router.get("/despacho/notas", response_class=HTMLResponse)
async def despacho_notas_page(request: Request):
    return _templates.TemplateResponse(request, "despacho_notas.html")


@router.get("/api/despacho/notas/filters")
async def get_despacho_notas_filters():
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT nombre_campo FROM appsheet.tarjas_pagos "
                "WHERE nombre_campo IS NOT NULL ORDER BY nombre_campo"
            )
            campos = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT contratista FROM appsheet.tarjas_pagos "
                "WHERE contratista IS NOT NULL ORDER BY contratista"
            )
            contratistas = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {"campos": campos, "contratistas": contratistas}


@router.get("/api/despacho/notas")
async def get_despacho_notas(
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
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["fecha::date BETWEEN %s AND %s", "contratista = %s"]
    params: list = [fecha_inicio, fecha_termino, contratista]

    if campo:
        filters.append("nombre_campo = %s")
        params.append(campo)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            # Detail rows grouped by tipo_pago, cc, labor
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

            # Totals by tipo_pago
            cur.execute(f"""
                SELECT
                    tipo_pago,
                    COALESCE(SUM(total_pagar), 0) AS total
                FROM appsheet.tarjas_pagos
                {where}
                GROUP BY tipo_pago
            """, params)
            totals_by_tipo = {r[0]: float(r[1]) for r in cur.fetchall()}

            # Campo / empresa info
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


# ===========================================================================
# Odoo export — CSV for Odoo purchase order import
# ===========================================================================

_ODOO_HEADERS = [
    "Vendedor",
    "Líneas del pedido/Producto/Nombre",
    "Líneas del pedido/Cantidad",
    "Líneas del pedido/Código de Distribución Analítica/Código",
    "Líneas del pedido/Precio un.",
    "",                                   # blank separator column (F)
    "partner_id",
    "order_line/product_id",
    "order_line/product_qty",
    "order_line/analytic_distribution",
    "order_line/price_unit",
]


def _parse_odoo_id(id_odoo_raw: Optional[str]) -> Tuple[str, str]:
    """Return (product_id_str, analytic_distribution_str) from raw id_odoo text.

    id_odoo is stored as e.g. '{"604": 100}\\r\\n' in the DB.
    Returns ('604', '{"604": 100}') or ('', '') on failure.
    """
    if not id_odoo_raw:
        return "", ""
    cleaned = id_odoo_raw.strip().rstrip("\\r\\n").strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            product_id = next(iter(parsed))
            return str(product_id), json.dumps(parsed)
    except (json.JSONDecodeError, StopIteration):
        pass
    return "", ""


@router.get("/despacho/odoo", response_class=HTMLResponse)
async def despacho_odoo_page(request: Request):
    return _templates.TemplateResponse(request, "despacho_notas.html")


@router.get("/api/despacho/odoo/filters")
async def get_despacho_odoo_filters():
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT cliente FROM appsheet.despacho_ingreso "
                "WHERE cliente IS NOT NULL ORDER BY cliente"
            )
            clientes = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {"clientes": clientes}


@router.get("/api/despacho/odoo/download")
async def download_despacho_odoo(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    cliente: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB connection failed: {exc}")

    filters = ["i.fecha_limpia::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if cliente:
        filters.append("i.cliente = %s")
        params.append(cliente)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    i.cliente,
                    cl.nombre_odoo              AS partner_id,
                    i.producto,
                    i.total_unidades,
                    cc.id_odoo
                FROM appsheet.despacho_ingreso i
                LEFT JOIN appsheet.despacho_cliente cl
                    ON TRIM(cl.cliente) = TRIM(i.cliente)
                LEFT JOIN appsheet.despacho_cc cc
                    ON TRIM(cc.producto) = TRIM(i.producto)
                {where}
                ORDER BY i.cliente, i.producto
            """, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_ODOO_HEADERS)

    prev_cliente = None
    for cliente_val, partner_id, producto, qty, id_odoo_raw in rows:
        product_id_str, analytic_dist = _parse_odoo_id(id_odoo_raw)

        # Vendedor only on first line per client (matches Odoo import format)
        vendedor_cell = cliente_val if cliente_val != prev_cliente else ""
        partner_cell  = (partner_id or cliente_val) if cliente_val != prev_cliente else ""
        prev_cliente  = cliente_val

        qty_val = int(qty) if qty is not None else ""

        writer.writerow([
            vendedor_cell,          # Vendedor
            producto or "",         # Producto/Nombre
            qty_val,                # Cantidad
            product_id_str,         # Código Distribución Analítica
            "",                     # Precio unitario (vacío — se completa en Odoo)
            "",                     # blank separator
            partner_cell,           # partner_id
            product_id_str,         # order_line/product_id
            qty_val,                # order_line/product_qty
            analytic_dist,          # order_line/analytic_distribution
            "",                     # order_line/price_unit
        ])

    output.seek(0)
    filename = f"odoo_despacho_{fecha_inicio}_{fecha_termino}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
