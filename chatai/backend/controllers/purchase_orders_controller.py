"""
controllers/purchase_orders_controller.py
------------------------------------------
HTTP layer for the Purchase Orders feature.

Routes:
  GET  /purchase-orders                   → Purchase order UI page
  GET  /api/purchase-orders/filters       → Dropdown options (contractors, companies)
  GET  /api/purchase-orders               → Order data filtered by params
  GET  /api/purchase-orders/odoo-export   → CSV export for Odoo import
"""

import datetime
import decimal
import io
import logging
import os
import re

import openpyxl
from google.cloud import bigquery
from google.oauth2 import service_account

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from auth import require_auth
from db import get_connection

logger = logging.getLogger("controllers.purchase_orders")


def _get_bq_client():
    key_path = os.getenv("BQ_KEY_PATH")
    project = os.getenv("BQ_PROJECT", "ace-scarab-484515-v1")
    credentials = service_account.Credentials.from_service_account_file(key_path)
    return bigquery.Client(project=project, credentials=credentials)


def _sync_labores(conn, fecha_inicio: str, fecha_termino: str, vendedor: str, nombre_campo: str):
    """Find labores without a product code in the given period and auto-map from BigQuery."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT r."Nombre Labor"
            FROM appsheet.tarjas_reporte r
            WHERE r.fecha BETWEEN %s AND %s
              AND r.contratista = %s
              AND r.nombre_campo = %s
              AND COALESCE(
                  (SELECT l.codigo_labor FROM appsheet.tarjas_labores l
                   WHERE TRIM(REGEXP_REPLACE(LOWER(l.labor), '\s+', ' ', 'g'))
                       = TRIM(REGEXP_REPLACE(LOWER(r."Nombre Labor"), '\s+', ' ', 'g'))
                   LIMIT 1),
                  (SELECT l.codigo_labor FROM appsheet.tarjas_labores l
                   WHERE r."Nombre Labor" ~ '^\[[\d.]+\]'
                     AND l.codigo_labor = TRIM(SUBSTRING(r."Nombre Labor" FROM '^\[([\d.]+)\]'))
                   LIMIT 1),
                  (SELECT l.codigo_labor FROM appsheet.tarjas_labores l
                   WHERE r."Nombre Labor" ~ '^[\d]+\.[\d]+-'
                     AND l.codigo_labor = TRIM(SUBSTRING(r."Nombre Labor" FROM '^([\d]+\.[\d]+)-'))
                   LIMIT 1)
              ) IS NULL
        """, (fecha_inicio, fecha_termino, vendedor, nombre_campo))
        unmapped = [row[0] for row in cur.fetchall()]

    if not unmapped:
        return

    bq = _get_bq_client()
    placeholders = ", ".join(f"'{labor.replace(chr(39), chr(39)*2)}'" for labor in unmapped)
    query = f"""
        SELECT
            JSON_VALUE(p.name, '$.es_CL') AS nombre,
            p.default_code                AS codigo
        FROM `ace-scarab-484515-v1.odoo_data.Producto` p
        WHERE p.default_code IS NOT NULL
          AND JSON_VALUE(p.name, '$.es_CL') IN ({placeholders})
    """
    results = bq.query(query).result()
    matches = {row.nombre: row.codigo for row in results}

    if not matches:
        return

    with conn.cursor() as cur:
        for labor, codigo in matches.items():
            cur.execute("""
                INSERT INTO appsheet.tarjas_labores (codigo_labor, labor)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (codigo, labor))
            logger.info(f"Auto-mapped labor: '{labor}' → {codigo}")
    conn.commit()

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Exact tipo_pago values from the DB
_PAYMENT_TYPE_TRATO = "trato"
_PAYMENT_TYPE_AL_DIA = "Al dia"


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def _serialize(v):
    """Convert DB types to JSON-safe Python types."""
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return str(v)
    return v


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/odoo/tarjas", response_class=HTMLResponse)
async def purchase_order_page(request: Request):
    return _templates.TemplateResponse(request, "purchase_orders.html")

@router.get("/purchase-orders", response_class=HTMLResponse)
async def purchase_order_legacy(request: Request):
    return RedirectResponse(url="/odoo/tarjas", status_code=301)


@router.get("/api/purchase-orders/filters")
async def get_filters():
    """Return distinct contractors and companies for the filter dropdowns."""
    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT contratista
                FROM appsheet.tarjas_reporte
                ORDER BY contratista
            """)
            contractors = [r[0] for r in cur.fetchall()]

            cur.execute("""
                SELECT DISTINCT nombre_campo
                FROM appsheet.tarjas_reporte
                ORDER BY nombre_campo
            """)
            companies = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return {"contratistas": contractors, "empresas": companies}


@router.get("/api/purchase-orders")
async def get_purchase_order(
    contratista: str,
    empresa: str,
    fecha_inicio: str,
    fecha_termino: str,
):
    """
    Return purchase order data for a contractor + company within a date range.
    The view tarjas_reporte partitions by (contratista, nombre_campo, fecha),
    so we aggregate totals here across the full range.
    """
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
                    contratista,
                    nombre_campo,
                    tipo_pago,
                    "CC",
                    "Nombre Labor",
                    SUM(jornadas)                                              AS jornadas,
                    CASE WHEN SUM(jornadas) > 0
                         THEN ROUND(SUM(total_labor)::numeric / SUM(jornadas), 2)
                         ELSE NULL END                                         AS total_unitario,
                    SUM(total_labor)                                           AS total_labor,
                    ROUND(
                        SUM(total_labor)::numeric
                        / NULLIF(SUM(SUM(total_labor)) OVER (PARTITION BY tipo_pago), 0) * 100,
                        2
                    )                                                          AS pct_pago
                FROM appsheet.tarjas_reporte
                WHERE contratista  = %s
                  AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                GROUP BY contratista, nombre_campo, tipo_pago, "CC", "Nombre Labor"
                ORDER BY tipo_pago DESC, "CC", "Nombre Labor"
            """, (contratista, empresa, fecha_inicio, fecha_termino))
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description]
    finally:
        conn.close()

    if not rows:
        return {"rows": [], "header": None}

    data = [{k: _serialize(v) for k, v in zip(columns, r)} for r in rows]

    total_trato  = sum(r["total_labor"] or 0 for r in data if r.get("tipo_pago") == _PAYMENT_TYPE_TRATO)
    total_al_dia = sum(r["total_labor"] or 0 for r in data if r.get("tipo_pago") == _PAYMENT_TYPE_AL_DIA)
    total_pagar  = total_trato + total_al_dia
    pct_trato    = round(total_trato  / total_pagar * 100, 1) if total_pagar else 0
    pct_al_dia   = round(total_al_dia / total_pagar * 100, 1) if total_pagar else 0

    header = {
        "contractor":   data[0]["contratista"],
        "company":      data[0]["nombre_campo"],
        "date_from":    fecha_inicio,
        "date_to":      fecha_termino,
        "total_trato":  total_trato,
        "total_al_dia": total_al_dia,
        "total":        total_pagar,
        "pct_trato":    pct_trato,
        "pct_al_dia":   pct_al_dia,
    }
    return {"header": header, "rows": data}


@router.get("/api/purchase-orders/odoo-export")
async def export_odoo_csv(
    contratista: str,
    empresa: str,
    fecha_inicio: str,
    fecha_termino: str,
):
    """
    Export tarjas_reporte_odoo as an .xlsx file ready for Odoo import.
    Format matches the manual upload template: partner_id only on first row.
    """
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    try:
        _sync_labores(conn, fecha_inicio, fecha_termino, contratista, empresa)
    except Exception as exc:
        logger.warning(f"Labor auto-sync failed (non-fatal): {exc}")

    excluded_amount = 0.0
    try:
        with conn.cursor() as cur:
            # Detect excluded rows (no product_id or unmapped CC) and sum their value
            cur.execute("""
                SELECT COALESCE(SUM("order_line/product_qty" * "order_line/price_unit"), 0)
                FROM appsheet.tarjas_reporte_odoo
                WHERE "Vendedor"     = %s
                  AND nombre_campo   = %s
                  AND fecha BETWEEN %s AND %s
                  AND (
                      "order_line/product_id" IS NULL
                      OR "order_line/analytic_distribution" LIKE '%%"": %%'
                  )
            """, (contratista, empresa, fecha_inicio, fecha_termino))
            excluded_amount = float(cur.fetchone()[0] or 0)

            cur.execute("""
                SELECT
                    "partner_id",
                    "order_line/product_id",
                    SUM("order_line/product_qty")               AS "order_line/product_qty",
                    "order_line/analytic_distribution",
                    CASE WHEN SUM("order_line/product_qty") > 0
                         THEN ROUND(
                             SUM("order_line/product_qty" * "order_line/price_unit")
                             / SUM("order_line/product_qty"), 2)
                         ELSE NULL END                          AS "order_line/price_unit"
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
            """, (contratista, empresa, fecha_inicio, fecha_termino))
            rows = cur.fetchall()
    finally:
        conn.close()

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

    for i, row in enumerate(rows):
        partner_id, product_id, qty, analytic, price = row
        ws.append([
            partner_id if i == 0 else None,
            product_id,
            float(qty) if qty is not None else None,
            analytic,
            float(price) if price is not None else None,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = (
        f"odoo_{contratista.replace(' ', '_')}_{empresa.replace(' ', '_')}"
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
