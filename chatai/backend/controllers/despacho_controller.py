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

  GET  /api/despacho/ordenes/sync-preview → CC sync status for sale orders
"""

import csv
import datetime
import decimal
import io
import json
import logging
import os
import re
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from google.cloud import bigquery
from google.oauth2 import service_account

from auth import require_auth
from db import get_connection

logger = logging.getLogger("controllers.despacho")

# ---------------------------------------------------------------------------
# BigQuery helpers (reuse same pattern as purchase_orders_controller)
# ---------------------------------------------------------------------------

_BQ_ALL_CC_QUERY = """
    SELECT
      CAST(id AS STRING) AS id,
      code,
      active,
      COALESCE(
        JSON_VALUE(name, '$.es_CL'),
        JSON_VALUE(name, '$.en_US'),
        CAST(id AS STRING)
      ) AS nombre
    FROM `ace-scarab-484515-v1.odoo_data.CC_analiticos`
"""


def _get_bq_client():
    # Support credentials from env var (base64 JSON, used in Cloud Run) or local file path
    key_b64 = os.getenv("BIGQUERY_KEY_B64")
    if key_b64:
        import base64
        import tempfile

        key_json = base64.b64decode(key_b64)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp.write(key_json)
        tmp.close()
        key_path = tmp.name
    else:
        key_path = os.getenv("BQ_KEY_PATH")

    project = os.getenv("BQ_PROJECT", "ace-scarab-484515-v1")
    credentials = service_account.Credentials.from_service_account_file(key_path)
    return bigquery.Client(project=project, credentials=credentials)


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
    return RedirectResponse(
        url=f"/api/tarjas/notas?{request.url.query}", status_code=301
    )


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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
    try:
        with conn.cursor() as cur:
            # Clientes — filtered by chofer if selected
            if chofer:
                cur.execute(
                    "SELECT DISTINCT cliente FROM appsheet.despacho_ingreso "
                    "WHERE cliente IS NOT NULL AND nombre_chofer = %s ORDER BY cliente",
                    (chofer,),
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
                    (cliente,),
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
            cur.execute(
                f"""
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
            """,
                params,
            )
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
                "fecha": r["fecha"],
                "cliente": r["cliente"],
                "nombre_odoo": r["nombre_odoo"],
                "chofer": r["chofer"],
                "patente": r["patente"],
                "destino": r["destino"],
                "lineas": [],
                "total_unidades": 0,
                "total_pallets": 0,
            }
        product_id, analytic = _parse_odoo_id(r["id_odoo"])
        trips[key]["lineas"].append(
            {
                "producto": r["producto"] or "—",
                "calidad": r["calidad"],
                "total_unidades": r["total_unidades"],
                "cajas": r["cajas"],
                "unidades_caja": r["unidades_caja"],
                "pallets": r["pallets"],
                "mallas": r["mallas"],
                "product_id": product_id,
                "analytic": analytic,
            }
        )
        trips[key]["total_unidades"] += r["total_unidades"]
        trips[key]["total_pallets"] += r["pallets"]

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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

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
            cur.execute(
                f"""
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
            """,
                params,
            )
            rows = _rows_to_dicts(cur)
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
            "Fecha",
            "Cliente",
            "Cliente Odoo",
            "Chofer",
            "Patente",
            "Destino",
            "Producto",
            "Cod. Odoo",
            "Calidad",
            "Total Unidades",
            "Cajas",
            "Und./Caja",
            "Pallets",
            "Mallas",
        ]
    )
    for r in rows:
        product_id, _ = _parse_odoo_id(r["id_odoo"])
        writer.writerow(
            [
                r["fecha"],
                r["cliente"],
                r["nombre_odoo"],
                r["chofer"],
                r["patente"],
                r["destino"],
                r["producto"],
                product_id,
                r["calidad"],
                r["total_unidades"],
                r["cajas"],
                r["unidades_caja"],
                r["pallets"],
                r["mallas"],
            ]
        )

    output.seek(0)
    filename = f"guia_despacho_{fecha_inicio}_{fecha_termino}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/despacho/guia/export-odoo")
async def export_guia_odoo(payload: dict = Body(...)):
    """Build Odoo import CSV from selected viajes passed directly from the frontend."""
    viajes: List[Any] = payload.get("viajes", [])
    if not viajes:
        raise HTTPException(status_code=400, detail="No viajes provided")

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_ODOO_HEADERS)

    prev_partner: str = ""
    for v in viajes:
        partner = v.get("nombre_odoo") or v.get("cliente") or ""
        for linea in v.get("lineas", []):
            product_id = linea.get("product_id") or ""
            analytic = linea.get("analytic") or ""
            qty = linea.get("total_unidades")
            qty_val = int(qty) if qty is not None else ""

            vendedor_cell = partner if partner != prev_partner else ""
            partner_cell = partner if partner != prev_partner else ""
            prev_partner = partner

            writer.writerow(
                [
                    vendedor_cell,
                    linea.get("producto") or "",
                    qty_val,
                    product_id,
                    "",
                    "",
                    partner_cell,
                    product_id,
                    qty_val,
                    analytic,
                    "",
                ]
            )

    output.seek(0)
    today = datetime.date.today().strftime("%Y-%m-%d")
    filename = f"odoo_guia_export_{today}.csv"
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    fecha_inicio: str = Query(None),
    fecha_termino: str = Query(None),
    cliente: str = Query(None),
    producto: str = Query(None),
):
    if fecha_inicio and not _DATE_RE.match(fecha_inicio):
        raise HTTPException(status_code=400, detail="fecha_inicio must be YYYY-MM-DD")
    if fecha_termino and not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="fecha_termino must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    filters = []
    params: list = []
    if fecha_inicio and fecha_termino:
        filters.append(
            "TO_DATE(SPLIT_PART(fecha, ' ', 1), 'MM/DD/YYYY') BETWEEN %s AND %s"
        )
        params.extend([fecha_inicio, fecha_termino])
    if cliente:
        filters.append("cliente = %s")
        params.append(cliente)
    if producto:
        filters.append("producto = %s")
        params.append(producto)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
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
            """,
                params,
            )
            ordenes = _rows_to_dicts(cur)

            cur.execute(
                f"""
                SELECT
                    COUNT(*)                                        AS total_ordenes,
                    COALESCE(SUM(NULLIF(cantidad, '')::numeric), 0) AS total_cantidad,
                    COUNT(DISTINCT cliente)                         AS total_clientes,
                    COUNT(DISTINCT centro_costo)                    AS total_ccs
                FROM appsheet.despacho_venta
                {where}
            """,
                params,
            )
            kpi = _rows_to_dicts(cur)[0]
    finally:
        conn.close()

    return {"ordenes": ordenes, "kpi": kpi}


@router.get("/api/despacho/ordenes/download")
async def download_despacho_ordenes(
    fecha_inicio: str = Query(None),
    fecha_termino: str = Query(None),
    cliente: str = Query(None),
    producto: str = Query(None),
):
    """CSV de órdenes de venta listo para importar en Odoo."""
    if fecha_inicio and not _DATE_RE.match(fecha_inicio):
        raise HTTPException(status_code=400, detail="fecha_inicio must be YYYY-MM-DD")
    if fecha_termino and not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="fecha_termino must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    filters = []
    params: list = []
    if fecha_inicio and fecha_termino:
        filters.append(
            "TO_DATE(SPLIT_PART(fecha, ' ', 1), 'MM/DD/YYYY') BETWEEN %s AND %s"
        )
        params.extend([fecha_inicio, fecha_termino])
    if cliente:
        filters.append("cliente = %s")
        params.append(cliente)
    if producto:
        filters.append("producto = %s")
        params.append(producto)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
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
            """,
                params,
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        ["Fecha", "Cliente", "Producto", "Descripción", "Centro de Costo", "Cantidad"]
    )
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
# Sync preview — CC status for sale orders
# ===========================================================================


@router.get("/api/despacho/ordenes/sync-preview")
async def get_despacho_ordenes_sync_preview(
    fecha_inicio: str = Query(None),
    fecha_termino: str = Query(None),
    cliente: str = Query(None),
    producto: str = Query(None),
):
    """
    Devuelve, para el período filtrado, el estado de cada Centro de Costo (CC)
    único presente en las órdenes de venta, validado contra BigQuery (CC_analiticos).

    Estado por CC:
      ok      → code existe y active = TRUE en Odoo
      unknown → no encontrado en CC_analiticos (o BQ no disponible)
      empty   → campo centro_costo vacío, NULL o valor '—'
    """
    if fecha_inicio and not _DATE_RE.match(fecha_inicio):
        raise HTTPException(status_code=400, detail="fecha_inicio must be YYYY-MM-DD")
    if fecha_termino and not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="fecha_termino must be YYYY-MM-DD")

    # 1. Fetch all CC_analiticos from BigQuery (best-effort)
    bq_available = False
    active_codes: set[str] = set()  # active CC codes (lower-stripped)
    all_codes: set[str] = set()  # all CC codes (lower-stripped) — active + archived
    try:
        bq = _get_bq_client()
        bq_rows = list(bq.query(_BQ_ALL_CC_QUERY).result())
        for r in bq_rows:
            code = str(r["code"]).strip().lower() if r["code"] else None
            if code:
                all_codes.add(code)
                if r["active"]:
                    active_codes.add(code)
        bq_available = True
    except Exception as exc:
        logger.warning(f"BigQuery no disponible en ordenes/sync-preview: {exc}")

    # 2. Fetch distinct CC values + aggregates from PostgreSQL
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    filters = []
    params: list = []
    if fecha_inicio and fecha_termino:
        filters.append(
            "TO_DATE(SPLIT_PART(fecha, ' ', 1), 'MM/DD/YYYY') BETWEEN %s AND %s"
        )
        params.extend([fecha_inicio, fecha_termino])
    if cliente:
        filters.append("cliente = %s")
        params.append(cliente)
    if producto:
        filters.append("producto = %s")
        params.append(producto)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COALESCE(centro_costo, '')                       AS cc,
                    COUNT(*)                                         AS num_ordenes,
                    COALESCE(SUM(NULLIF(cantidad, '')::numeric), 0)  AS total_cantidad
                FROM appsheet.despacho_venta
                {where}
                GROUP BY centro_costo
                ORDER BY centro_costo
            """,
                params,
            )
            cc_rows = cur.fetchall()
    finally:
        conn.close()

    # 3. Classify each CC
    result = []
    ok_count = unknown_count = empty_count = 0

    for cc_raw, num_ordenes, total_cantidad in cc_rows:
        cc_val = (cc_raw or "").strip()
        is_empty = not cc_val or cc_val == "—"

        if is_empty:
            status = "empty"
            empty_count += 1
        elif not bq_available:
            status = "unknown"
            unknown_count += 1
        else:
            cc_lower = cc_val.lower()
            if cc_lower in active_codes:
                status = "ok"
                ok_count += 1
            elif cc_lower in all_codes:
                # Exists in Odoo but archived
                status = "archived"
                unknown_count += 1
            else:
                status = "unknown"
                unknown_count += 1

        result.append(
            {
                "cc": cc_val if cc_val else "—",
                "num_ordenes": int(num_ordenes),
                "total_cantidad": float(total_cantidad),
                "status": status,
            }
        )

    return {
        "ccs": result,
        "bq_available": bq_available,
        "ok_count": ok_count,
        "unknown_count": unknown_count,
        "empty_count": empty_count,
        "total": len(result),
    }


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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    base_filters = ["fecha_limpia::date BETWEEN %s AND %s"]
    base_params: list = [fecha_inicio, fecha_termino]
    if cliente:
        base_filters.append("cliente = %s")
        base_params.append(cliente)
    where = "WHERE " + " AND ".join(base_filters)

    try:
        with conn.cursor() as cur:
            # ── KPIs globales ──
            cur.execute(
                f"""
                SELECT
                    COUNT(*)                                    AS total_registros,
                    COALESCE(SUM(kg_brutos), 0)                AS total_kg,
                    COALESCE(SUM(total_bins), 0)               AS total_bins,
                    COALESCE(SUM(total_unidades), 0)           AS total_unidades,
                    COUNT(DISTINCT cliente)                     AS clientes,
                    COUNT(DISTINCT fecha_limpia::date)          AS dias
                FROM appsheet.despacho_ingreso
                {where}
            """,
                base_params,
            )
            kpi = _rows_to_dicts(cur)[0]

            # ── Tendencia semanal (unidades) ──
            cur.execute(
                f"""
                SELECT
                    DATE_TRUNC('week', fecha_limpia::timestamp)::date AS semana,
                    COALESCE(SUM(total_unidades), 0)                  AS unidades,
                    COALESCE(SUM(kg_brutos), 0)                       AS kg,
                    COUNT(*)                                          AS registros
                FROM appsheet.despacho_ingreso
                {where}
                GROUP BY 1 ORDER BY 1
            """,
                base_params,
            )
            tendencia_semanal = _rows_to_dicts(cur)

            # ── Top clientes por unidades ──
            cur.execute(
                f"""
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
            """,
                base_params,
            )
            top_clientes = _rows_to_dicts(cur)

            # ── Distribución por calidad (solo registros con unidades) ──
            cur.execute(
                f"""
                SELECT
                    COALESCE(calidad, 'Sin calidad')            AS calidad,
                    COALESCE(SUM(total_unidades), 0)            AS unidades,
                    COUNT(*)                                    AS registros
                FROM appsheet.despacho_ingreso
                {where} AND total_unidades > 0
                GROUP BY calidad
                ORDER BY unidades DESC
            """,
                base_params,
            )
            por_calidad = _rows_to_dicts(cur)

            # ── Top productos (unidades, semillas/pimientos) ──
            cur.execute(
                f"""
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
            """,
                base_params,
            )
            top_productos = _rows_to_dicts(cur)

            # ── Últimos 10 despachos ──
            cur.execute(
                f"""
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
            """,
                base_params,
            )
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
    "",  # blank separator column (F)
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    filters = ["i.fecha_limpia::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]

    if cliente:
        filters.append("i.cliente = %s")
        params.append(cliente)

    where = "WHERE " + " AND ".join(filters)

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
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
            """,
                params,
            )
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
        partner_cell = (
            (partner_id or cliente_val) if cliente_val != prev_cliente else ""
        )
        prev_cliente = cliente_val

        qty_val = int(qty) if qty is not None else ""

        writer.writerow(
            [
                vendedor_cell,  # Vendedor
                producto or "",  # Producto/Nombre
                qty_val,  # Cantidad
                product_id_str,  # Código Distribución Analítica
                "",  # Precio unitario (vacío — se completa en Odoo)
                "",  # blank separator
                partner_cell,  # partner_id
                product_id_str,  # order_line/product_id
                qty_val,  # order_line/product_qty
                analytic_dist,  # order_line/analytic_distribution
                "",  # order_line/price_unit
            ]
        )

    output.seek(0)
    filename = f"odoo_despacho_{fecha_inicio}_{fecha_termino}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
