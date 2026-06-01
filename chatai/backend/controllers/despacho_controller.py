"""
controllers/despacho_controller.py
-----------------------------------
HTTP layer for Despacho reports.

Routes:
  GET  /despacho/notas                  → redirect 301 → /tarjas/notas
  GET  /api/despacho/notas/filters      → redirect 301
  GET  /api/despacho/notas              → redirect 301

  GET  /despacho/resumen                → Resumen de despacho page
  GET  /api/despacho/resumen/filters    → Filter options (clientes, fechas)
  GET  /api/despacho/resumen            → Dashboard data

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
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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
# Notas de crédito — moved to /tarjas/notas (redirects kept for old bookmarks)
# ===========================================================================

@router.get("/despacho/notas")
async def despacho_notas_redirect():
    return RedirectResponse(url="/tarjas/notas", status_code=301)


@router.get("/api/despacho/notas/filters")
async def redirect_despacho_notas_filters():
    return RedirectResponse(url="/api/tarjas/notas/filters", status_code=301)


@router.get("/api/despacho/notas")
async def redirect_despacho_notas(request: Request):
    return RedirectResponse(url=f"/api/tarjas/notas?{request.url.query}", status_code=301)


# ===========================================================================
# Odoo export — CSV for Odoo purchase order import
# ===========================================================================

# ===========================================================================
# Guía de despacho — document view
# ===========================================================================

@router.get("/despacho/guia", response_class=HTMLResponse)
async def despacho_guia_page(request: Request):
    return _templates.TemplateResponse(request, "despacho_guia.html")


@router.get("/api/despacho/guia/filters")
async def get_despacho_guia_filters(
    cliente: str = Query(None),
    chofer: str = Query(None),
):
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            # Clientes — filtered by chofer if selected
            if chofer:
                cur.execute(
                    "SELECT DISTINCT cliente FROM appsheet.despacho_ingreso "
                    "WHERE cliente IS NOT NULL AND nombre_chofer = %s ORDER BY cliente",
                    (chofer,)
                )
            else:
                cur.execute(
                    "SELECT DISTINCT cliente FROM appsheet.despacho_ingreso "
                    "WHERE cliente IS NOT NULL ORDER BY cliente"
                )
            clientes = [r[0] for r in cur.fetchall()]

            # Choferes — filtered by cliente if selected
            if cliente:
                cur.execute(
                    "SELECT DISTINCT nombre_chofer FROM appsheet.despacho_ingreso "
                    "WHERE nombre_chofer IS NOT NULL AND cliente = %s ORDER BY nombre_chofer",
                    (cliente,)
                )
            else:
                cur.execute(
                    "SELECT DISTINCT nombre_chofer FROM appsheet.despacho_ingreso "
                    "WHERE nombre_chofer IS NOT NULL ORDER BY nombre_chofer"
                )
            choferes = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    return {"clientes": clientes, "choferes": choferes}


@router.get("/api/despacho/guia")
async def get_despacho_guia(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    cliente: str = Query(None),
    chofer: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["i.fecha_limpia::date BETWEEN %s AND %s", "i.total_unidades > 0"]
    params: list = [fecha_inicio, fecha_termino]
    if cliente:
        filters.append("i.cliente = %s")
        params.append(cliente)
    if chofer:
        filters.append("i.nombre_chofer = %s")
        params.append(chofer)
    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    i.fecha_limpia::date::text          AS fecha,
                    COALESCE(i.cliente, '—')            AS cliente,
                    COALESCE(cl.nombre_odoo, i.cliente) AS nombre_odoo,
                    COALESCE(i.nombre_chofer, '—')      AS chofer,
                    COALESCE(i.numero_patente, '—')     AS patente,
                    COALESCE(i.destino, '—')            AS destino,
                    i.producto,
                    cc.id_odoo,
                    COALESCE(i.calidad, '—')            AS calidad,
                    COALESCE(i.total_unidades, 0)       AS total_unidades,
                    COALESCE(i.cajas, 0)                AS cajas,
                    COALESCE(i.unidades_caja, 0)        AS unidades_caja,
                    COALESCE(i.cantidad_de_pallet, 0)   AS pallets,
                    COALESCE(i.mallas, 0)               AS mallas
                FROM appsheet.despacho_ingreso i
                LEFT JOIN appsheet.despacho_cliente cl
                    ON TRIM(cl.cliente) = TRIM(i.cliente)
                LEFT JOIN appsheet.despacho_cc cc
                    ON TRIM(cc.producto) = TRIM(i.producto)
                {where}
                ORDER BY i.fecha_limpia DESC, i.cliente, i.producto
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    # Group rows into trips: key = (fecha, cliente, chofer, patente)
    from collections import OrderedDict
    trips: dict = OrderedDict()
    for r in rows:
        key = (r["fecha"], r["cliente"], r["chofer"], r["patente"])
        if key not in trips:
            trips[key] = {
                "fecha":      r["fecha"],
                "cliente":    r["cliente"],
                "nombre_odoo": r["nombre_odoo"],
                "chofer":     r["chofer"],
                "patente":    r["patente"],
                "destino":    r["destino"],
                "lineas":     [],
                "total_unidades": 0,
                "total_pallets":  0,
            }
        product_id, analytic = _parse_odoo_id(r["id_odoo"])
        trips[key]["lineas"].append({
            "producto":       r["producto"] or "—",
            "calidad":        r["calidad"],
            "total_unidades": r["total_unidades"],
            "cajas":          r["cajas"],
            "unidades_caja":  r["unidades_caja"],
            "pallets":        r["pallets"],
            "mallas":         r["mallas"],
            "product_id":     product_id,
            "analytic":       analytic,
        })
        trips[key]["total_unidades"] += r["total_unidades"]
        trips[key]["total_pallets"]  += r["pallets"]

    return {"viajes": list(trips.values())}


@router.get("/api/despacho/guia/download")
async def download_despacho_guia(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    cliente: str = Query(None),
    chofer: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = ["i.fecha_limpia::date BETWEEN %s AND %s", "i.total_unidades > 0"]
    params: list = [fecha_inicio, fecha_termino]
    if cliente:
        filters.append("i.cliente = %s")
        params.append(cliente)
    if chofer:
        filters.append("i.nombre_chofer = %s")
        params.append(chofer)
    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    i.fecha_limpia::date::text          AS fecha,
                    COALESCE(i.cliente, '')             AS cliente,
                    COALESCE(cl.nombre_odoo, i.cliente, '') AS nombre_odoo,
                    COALESCE(i.nombre_chofer, '')       AS chofer,
                    COALESCE(i.numero_patente, '')      AS patente,
                    COALESCE(i.destino, '')             AS destino,
                    COALESCE(i.producto, '')            AS producto,
                    cc.id_odoo,
                    COALESCE(i.calidad, '')             AS calidad,
                    COALESCE(i.total_unidades, 0)       AS total_unidades,
                    COALESCE(i.cajas, 0)                AS cajas,
                    COALESCE(i.unidades_caja, 0)        AS unidades_caja,
                    COALESCE(i.cantidad_de_pallet, 0)   AS pallets,
                    COALESCE(i.mallas, 0)               AS mallas
                FROM appsheet.despacho_ingreso i
                LEFT JOIN appsheet.despacho_cliente cl
                    ON TRIM(cl.cliente) = TRIM(i.cliente)
                LEFT JOIN appsheet.despacho_cc cc
                    ON TRIM(cc.producto) = TRIM(i.producto)
                {where}
                ORDER BY i.fecha_limpia DESC, i.cliente, i.producto
            """, params)
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Fecha", "Cliente", "Cliente Odoo", "Chofer", "Patente", "Destino",
        "Producto", "Cod. Odoo", "Calidad",
        "Total Unidades", "Cajas", "Und./Caja", "Pallets", "Mallas",
    ])
    for r in rows:
        product_id, _ = _parse_odoo_id(r["id_odoo"])
        writer.writerow([
            r["fecha"], r["cliente"], r["nombre_odoo"],
            r["chofer"], r["patente"], r["destino"],
            r["producto"], product_id, r["calidad"],
            r["total_unidades"], r["cajas"], r["unidades_caja"],
            r["pallets"], r["mallas"],
        ])

    output.seek(0)
    filename = f"guia_despacho_{fecha_inicio}_{fecha_termino}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===========================================================================
# Órdenes de venta — despacho_resumen table
# ===========================================================================

@router.get("/despacho/ordenes", response_class=HTMLResponse)
async def despacho_ordenes_page(request: Request):
    return _templates.TemplateResponse(request, "despacho_ordenes.html")


@router.get("/api/despacho/ordenes/filters")
async def get_despacho_ordenes_filters():
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT cliente FROM appsheet.despacho_venta "
                "WHERE cliente IS NOT NULL ORDER BY cliente"
            )
            clientes = [r[0] for r in cur.fetchall()]

            cur.execute(
                "SELECT DISTINCT producto FROM appsheet.despacho_venta "
                "WHERE producto IS NOT NULL ORDER BY producto"
            )
            productos = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    return {"clientes": clientes, "productos": productos}


@router.get("/api/despacho/ordenes")
async def get_despacho_ordenes(
    cliente: str = Query(None),
    producto: str = Query(None),
):
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = []
    params: list = []
    if cliente:
        filters.append("cliente = %s")
        params.append(cliente)
    if producto:
        filters.append("producto = %s")
        params.append(producto)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    COALESCE(cliente, '—')          AS cliente,
                    COALESCE(producto, '—')         AS producto,
                    COALESCE(descripcion, '—')      AS descripcion,
                    COALESCE(cantidad, '0')         AS cantidad,
                    COALESCE(centro_costo, '—')     AS cc,
                    fecha
                FROM appsheet.despacho_venta
                {where}
                ORDER BY fecha DESC, cliente, producto
            """, params)
            ordenes = _rows_to_dicts(cur)

            cur.execute(f"""
                SELECT
                    COUNT(*)                                        AS total_ordenes,
                    COALESCE(SUM(NULLIF(cantidad, '')::numeric), 0) AS total_cantidad,
                    COUNT(DISTINCT cliente)                         AS total_clientes,
                    COUNT(DISTINCT centro_costo)                    AS total_ccs
                FROM appsheet.despacho_venta
                {where}
            """, params)
            kpi = _rows_to_dicts(cur)[0]
    finally:
        conn.close()

    return {"ordenes": ordenes, "kpi": kpi}


@router.get("/api/despacho/ordenes/download")
async def download_despacho_ordenes(
    cliente: str = Query(None),
    producto: str = Query(None),
):
    """CSV de órdenes de venta listo para importar en Odoo."""
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    filters = []
    params: list = []
    if cliente:
        filters.append("cliente = %s")
        params.append(cliente)
    if producto:
        filters.append("producto = %s")
        params.append(producto)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    COALESCE(cliente, '')     AS cliente,
                    COALESCE(producto, '')    AS producto,
                    COALESCE(descripcion, '') AS descripcion,
                    COALESCE(cantidad, '0')   AS cantidad,
                    COALESCE(centro_costo, '') AS centro_costo,
                    fecha
                FROM appsheet.despacho_venta
                {where}
                ORDER BY fecha DESC, cliente, producto
            """, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["Fecha", "Cliente", "Producto", "Descripción", "Centro de Costo", "Cantidad"])
    for r in rows:
        writer.writerow([r[5], r[0], r[1], r[2], r[4], r[3]])

    output.seek(0)
    today = datetime.date.today().strftime("%Y-%m-%d")
    filename = f"ordenes_venta_{today}.csv"
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===========================================================================
# Resumen de despacho — dashboard view
# ===========================================================================

@router.get("/despacho/resumen", response_class=HTMLResponse)
async def despacho_resumen_page(request: Request):
    return _templates.TemplateResponse(request, "despacho_resumen.html")


@router.get("/api/despacho/resumen/filters")
async def get_despacho_resumen_filters():
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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


@router.get("/api/despacho/resumen")
async def get_despacho_resumen(
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    cliente: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    base_filters = ["fecha_limpia::date BETWEEN %s AND %s"]
    base_params: list = [fecha_inicio, fecha_termino]
    if cliente:
        base_filters.append("cliente = %s")
        base_params.append(cliente)
    where = "WHERE " + " AND ".join(base_filters)

    try:
        with conn.cursor() as cur:
            # ── KPIs globales ──
            cur.execute(f"""
                SELECT
                    COUNT(*)                                    AS total_registros,
                    COALESCE(SUM(kg_brutos), 0)                AS total_kg,
                    COALESCE(SUM(total_bins), 0)               AS total_bins,
                    COALESCE(SUM(total_unidades), 0)           AS total_unidades,
                    COUNT(DISTINCT cliente)                     AS clientes,
                    COUNT(DISTINCT fecha_limpia::date)          AS dias
                FROM appsheet.despacho_ingreso
                {where}
            """, base_params)
            kpi = _rows_to_dicts(cur)[0]

            # ── Tendencia semanal (unidades) ──
            cur.execute(f"""
                SELECT
                    DATE_TRUNC('week', fecha_limpia::timestamp)::date AS semana,
                    COALESCE(SUM(total_unidades), 0)                  AS unidades,
                    COALESCE(SUM(kg_brutos), 0)                       AS kg,
                    COUNT(*)                                          AS registros
                FROM appsheet.despacho_ingreso
                {where}
                GROUP BY 1 ORDER BY 1
            """, base_params)
            tendencia_semanal = _rows_to_dicts(cur)

            # ── Top clientes por unidades ──
            cur.execute(f"""
                SELECT
                    COALESCE(cliente, 'Sin cliente')            AS cliente,
                    COALESCE(SUM(total_unidades), 0)            AS unidades,
                    COALESCE(SUM(kg_brutos), 0)                 AS kg,
                    COUNT(*)                                    AS despachos
                FROM appsheet.despacho_ingreso
                {where}
                GROUP BY cliente
                ORDER BY unidades DESC, kg DESC
                LIMIT 10
            """, base_params)
            top_clientes = _rows_to_dicts(cur)

            # ── Distribución por calidad (solo registros con unidades) ──
            cur.execute(f"""
                SELECT
                    COALESCE(calidad, 'Sin calidad')            AS calidad,
                    COALESCE(SUM(total_unidades), 0)            AS unidades,
                    COUNT(*)                                    AS registros
                FROM appsheet.despacho_ingreso
                {where} AND total_unidades > 0
                GROUP BY calidad
                ORDER BY unidades DESC
            """, base_params)
            por_calidad = _rows_to_dicts(cur)

            # ── Top productos (unidades, semillas/pimientos) ──
            cur.execute(f"""
                SELECT
                    CASE
                        WHEN producto LIKE '%%-25/26 %%'
                            THEN SPLIT_PART(producto, '-25/26 ', 2)
                        ELSE COALESCE(producto, 'Sin producto')
                    END                                         AS producto,
                    COALESCE(SUM(total_unidades), 0)            AS unidades,
                    COUNT(*)                                    AS registros
                FROM appsheet.despacho_ingreso
                {where} AND total_unidades > 0
                GROUP BY 1
                ORDER BY unidades DESC
                LIMIT 10
            """, base_params)
            top_productos = _rows_to_dicts(cur)

            # ── Últimos 10 despachos ──
            cur.execute(f"""
                SELECT
                    fecha_limpia::date::text        AS fecha,
                    COALESCE(cliente, '—')          AS cliente,
                    COALESCE(producto, '—')         AS producto,
                    COALESCE(calidad, '—')          AS calidad,
                    COALESCE(total_unidades, 0)     AS unidades,
                    COALESCE(kg_brutos, 0)          AS kg,
                    COALESCE(total_bins, 0)         AS bins
                FROM appsheet.despacho_ingreso
                {where}
                ORDER BY fecha_limpia DESC
                LIMIT 15
            """, base_params)
            ultimos = _rows_to_dicts(cur)

    finally:
        conn.close()

    return {
        "kpi": kpi,
        "tendencia_semanal": tendencia_semanal,
        "top_clientes": top_clientes,
        "por_calidad": por_calidad,
        "top_productos": top_productos,
        "ultimos": ultimos,
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
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
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

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
