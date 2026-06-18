"""
controllers/purchase_orders_controller.py
------------------------------------------
HTTP layer for the Purchase Orders feature.

Routes:
  GET  /purchase-orders                   → Purchase order UI page
  GET  /api/purchase-orders/filters       → Dropdown options (contractors, companies)
  GET  /api/purchase-orders               → Order data filtered by params
  GET  /api/purchase-orders/odoo-export   → CSV export for Odoo import
  GET  /odoo/facturacion                  → Billing order UI page
  GET  /api/odoo/facturacion/pdf          → PDF of billing order (opens in new tab)
  GET  /api/tarjas/cc-status              → CC sync status (archived IDs detection)
  POST /api/tarjas/sync-cc                → Trigger CC sync on demand
"""

import datetime
import decimal
import io
import json as _json
import logging
import os
import re

import openpyxl
from xhtml2pdf import pisa
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


@router.get("/odoo/facturacion", response_class=HTMLResponse)
async def billing_order_page(request: Request):
    return _templates.TemplateResponse(request, "billing_order.html")


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


# ---------------------------------------------------------------------------
# CC sync status and on-demand sync
# ---------------------------------------------------------------------------

_BQ_CC_QUERY = """
    SELECT
      CAST(id AS STRING) AS id,
      code,
      COALESCE(
        JSON_VALUE(name, '$.es_CL'),
        JSON_VALUE(name, '$.en_US'),
        CAST(id AS STRING)
      ) AS nombre
    FROM `ace-scarab-484515-v1.odoo_data.CC_analiticos`
    WHERE active = TRUE
      AND code IS NOT NULL AND TRIM(code) != ''
"""


@router.get("/api/tarjas/cc-status")
async def get_cc_status():
    """
    Compara los IDs almacenados en tarjas_cc.valor_odoo contra los CC activos en Odoo (BigQuery).
    Devuelve por cada CC si está ok, archivado o vacío, y la fecha de último sync.
    """
    # 1. Active Odoo CC from BigQuery
    active_ids: set[str] | None = None
    bq_available = False
    try:
        bq = _get_bq_client()
        bq_rows = list(bq.query(_BQ_CC_QUERY).result())
        active_ids = {r["id"] for r in bq_rows}
        bq_available = True
    except Exception as exc:
        logger.warning(f"BigQuery no disponible para cc-status: {exc}")

    # 2. tarjas_cc and last sync time from PostgreSQL
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    cc_rows = []
    last_sync = None
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT id_cc::text, cultivo, valor_odoo FROM appsheet.tarjas_cc ORDER BY id_cc::int"
                )
                cc_rows = cur.fetchall()
            except Exception as exc:
                logger.warning(f"No se pudo leer tarjas_cc: {exc}")

            try:
                cur.execute("SELECT value FROM appsheet.sync_meta WHERE key = 'last_cc_sync'")
                meta = cur.fetchone()
                last_sync = meta[0] if meta else None
            except Exception:
                pass
    finally:
        conn.close()

    # 3. Classify each CC entry
    result = []
    ok_count = archived_count = empty_count = unknown_count = 0

    for id_cc, cultivo, valor_odoo in cc_rows:
        stored_ids: list[str] = []
        if isinstance(valor_odoo, dict):
            stored_ids = [k for k in valor_odoo.keys() if k != ""]
        elif isinstance(valor_odoo, str):
            try:
                parsed = _json.loads(valor_odoo)
                stored_ids = [k for k in parsed.keys() if k != ""]
            except Exception:
                pass

        if not stored_ids:
            status = "empty"
            empty_count += 1
        elif active_ids is None:
            status = "unknown"
            unknown_count += 1
        else:
            archived = [sid for sid in stored_ids if sid not in active_ids]
            if archived:
                status = "archived"
                archived_count += 1
            else:
                status = "ok"
                ok_count += 1

        result.append({
            "id_cc": id_cc,
            "cultivo": cultivo,
            "stored_ids": stored_ids,
            "status": status,
        })

    return {
        "ccs": result,
        "last_sync": last_sync,
        "bq_available": bq_available,
        "ok_count": ok_count,
        "archived_count": archived_count,
        "empty_count": empty_count,
        "unknown_count": unknown_count,
        "total": len(result),
    }


@router.post("/api/tarjas/sync-cc")
async def trigger_cc_sync():
    """
    Sincroniza tarjas_cc.valor_odoo contra los CC activos en Odoo.
    Corrige mappings simples (ID único archivado) y registra el timestamp del sync.
    Las distribuciones multi-CC se dejan para revisión manual.
    """
    # 1. Fetch active CC from BigQuery
    try:
        bq = _get_bq_client()
        bq_rows = list(bq.query(_BQ_CC_QUERY).result())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"BigQuery no disponible: {exc}")

    by_code: dict[str, dict] = {}
    active_ids: set[str] = set()
    for r in bq_rows:
        code = str(r["code"]).strip()
        active_ids.add(r["id"])
        if code not in by_code:
            by_code[code] = {"id": r["id"], "nombre": r["nombre"]}

    # 2. Fetch current tarjas_cc
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    fixed = 0
    now_iso = datetime.datetime.utcnow().isoformat()

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id_cc::text, valor_odoo FROM appsheet.tarjas_cc")
            existing = cur.fetchall()

        to_fix: list[tuple[str, str]] = []
        for id_cc, valor_odoo in existing:
            stored = valor_odoo if isinstance(valor_odoo, dict) else {}
            if isinstance(valor_odoo, str):
                try:
                    stored = _json.loads(valor_odoo)
                except Exception:
                    stored = {}

            stored_keys = [k for k in stored.keys() if k != ""]

            if not stored_keys or list(stored.keys()) == [""]:
                # Empty → fill if code is known
                code = str(id_cc).strip()
                if code in by_code:
                    to_fix.append((_json.dumps({by_code[code]["id"]: 100}), id_cc))
            elif len(stored_keys) == 1 and stored_keys[0] not in active_ids:
                # Single stale ID → replace
                code = str(id_cc).strip()
                if code in by_code:
                    to_fix.append((_json.dumps({by_code[code]["id"]: 100}), id_cc))
                # If code not in by_code, we can't auto-fix — leave for manual review

        with conn.cursor() as cur:
            for new_json, id_cc in to_fix:
                cur.execute(
                    "UPDATE appsheet.tarjas_cc SET valor_odoo = %s::jsonb WHERE id_cc = %s",
                    (new_json, id_cc),
                )
                fixed += 1

            cur.execute("""
                CREATE TABLE IF NOT EXISTS appsheet.sync_meta (
                    key TEXT PRIMARY KEY, value TEXT
                )
            """)
            cur.execute("""
                INSERT INTO appsheet.sync_meta (key, value) VALUES ('last_cc_sync', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (now_iso,))

        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error en sincronización: {exc}")
    finally:
        conn.close()

    return {
        "fixed": fixed,
        "synced_at": now_iso,
        "message": f"Sync completado: {fixed} CC actualizados.",
    }


# ---------------------------------------------------------------------------
# Billing order PDF
# ---------------------------------------------------------------------------

_PDF_CSS = """
@page { size: A4 landscape; margin: 12mm 14mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 8pt; color: #111; margin: 0; }

/* ── Header uses real <table> for xhtml2pdf compat ── */
.hdr-table { width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1;
             margin-bottom: 10px; }
.hdr-logo  { width: 80px; padding: 10px 12px; vertical-align: middle; text-align: center;
             border-right: 1px solid #e2e8f0; }
.hdr-logo-box {
  width: 58px; height: 58px; border: 2px solid #e2e8f0;
  font-size: 7pt; font-weight: bold; color: #64748b; line-height: 1.4;
  background: #f8fafc; text-align: center; padding-top: 14px;
}
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

/* ── Glosa uses real <table> ── */
.glosa-table { width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1;
               margin-bottom: 10px; }
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

/* ── Pivot table ── */
.pivot-title { font-size: 9pt; font-weight: bold; margin: 8px 0 4px; color: #1e293b; }
.pivot-table { width: 100%; border-collapse: collapse; font-size: 7.5pt; }
.pivot-table thead tr { background: #1d4ed8; color: white; }
.pivot-table thead th { padding: 6px 8px; text-align: left; font-weight: bold; white-space: nowrap; }
.pivot-table thead th.num { text-align: right; }
.pivot-table tbody tr.even { background: #f8fafc; }
.pivot-table tbody td { padding: 4px 8px; border-bottom: 1px solid #f1f5f9; white-space: nowrap; }
.pivot-table td.num  { text-align: right; }
.pivot-table td.tot  { text-align: right; font-weight: bold; background: #fef9c3; }
.pivot-table tr.foot td {
  font-weight: bold; background: #1e293b; color: white;
  text-align: right; border: none; padding: 6px 8px;
}
.pivot-table tr.foot td:first-child { text-align: left; }
"""


def _fmt_clp(v) -> str:
    try:
        return f"${int(float(v or 0)):,}".replace(",", ".")
    except Exception:
        return "-"


def _fmt_date_display(iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(iso)
        months = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
        return f"{d.day} {months[d.month-1]} {d.year}"
    except Exception:
        return iso


def _fmt_date_short(iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(iso)
        return f"{d.day}/{d.month}"
    except Exception:
        return iso


@router.get("/api/odoo/facturacion/pdf")
async def billing_order_pdf(
    contratista: str,
    empresa: str,
    fecha_inicio: str,
    fecha_termino: str,
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    try:
        with conn.cursor() as cur:
            # Header totals (same query as get_purchase_order)
            cur.execute("""
                SELECT tipo_pago, SUM(total_labor) AS total_labor
                FROM appsheet.tarjas_reporte
                WHERE contratista  = %s
                  AND nombre_campo = %s
                  AND fecha BETWEEN %s AND %s
                GROUP BY tipo_pago
            """, (contratista, empresa, fecha_inicio, fecha_termino))
            tipo_rows = cur.fetchall()

            # Pivot data: worker × date
            cur.execute("""
                SELECT trabajador, fecha::date::text AS fecha,
                       SUM(total_trabajado) AS total
                FROM appsheet.tarjas_pagos
                WHERE contratista  = %s
                  AND nombre_campo = %s
                  AND fecha::date BETWEEN %s AND %s
                GROUP BY trabajador, fecha::date
                ORDER BY trabajador, fecha::date
            """, (contratista, empresa, fecha_inicio, fecha_termino))
            pivot_rows = cur.fetchall()
    finally:
        conn.close()

    # Compute totals
    total_trato  = sum(float(r[1] or 0) for r in tipo_rows if r[0] == "trato")
    total_al_dia = sum(float(r[1] or 0) for r in tipo_rows if r[0] != "trato")
    total_pagar  = total_trato + total_al_dia

    # Build pivot structure
    dates: list[str] = sorted({r[1] for r in pivot_rows if r[1]})
    workers: dict[str, dict] = {}
    for worker, fecha, total in pivot_rows:
        w = worker or "(sin nombre)"
        if w not in workers:
            workers[w] = {}
        workers[w][fecha] = float(total or 0)

    sorted_workers = sorted(workers.items())

    # Column totals
    col_totals = {d: sum(wdata.get(d, 0) for _, wdata in sorted_workers) for d in dates}
    grand_total = sum(col_totals.values())

    # ── HTML ──
    d1 = _fmt_date_display(fecha_inicio)
    d2 = _fmt_date_display(fecha_termino)
    glosa = f"SERVICIOS DE LABORES AGRÍCOLAS {d1.upper()} AL {d2.upper()}"
    semana = f"Semana desde {d1} al {d2}"

    date_headers = "".join(f'<th class="num">{_fmt_date_short(d)}</th>' for d in dates)

    rows_html = ""
    for worker, wdata in sorted_workers:
        row_total = sum(wdata.get(d, 0) for d in dates)
        cells = ""
        for d in dates:
            v = wdata.get(d, 0)
            cells += f'<td class="num">{_fmt_clp(v) if v else "-"}</td>'
        even_cls = "even" if len(rows_html) % 2 == 0 else ""
        rows_html += (
            f'<tr class="{even_cls}"><td>{worker}</td>{cells}'
            f'<td class="tot">{_fmt_clp(row_total)}</td></tr>'
        )

    foot_cells = "".join(f'<td>{_fmt_clp(col_totals[d])}</td>' for d in dates)
    foot_html = f'<tr class="foot"><td>Suma total</td>{foot_cells}<td>{_fmt_clp(grand_total)}</td></tr>'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Orden de Facturación — {contratista}</title>
<style>{_PDF_CSS}</style>
</head><body>

<!-- Header: 3 columns using real table -->
<table class="hdr-table">
  <tr>
    <td class="hdr-logo">
      <div class="hdr-logo-box">EMPRESAS<br>DONAR</div>
    </td>
    <td class="hdr-mid">
      <p class="co-name">{empresa}</p>
      <p class="co-sub">Contratista: {contratista}</p>
      <p class="co-week">{semana}</p>
    </td>
    <td class="hdr-right">
      <p class="dt-row">
        <span class="dt-label">Fecha Inicio&nbsp;&nbsp;</span>
        <span class="dt-val">{_fmt_date_display(fecha_inicio)}</span>
      </p>
      <p class="dt-row">
        <span class="dt-label">Fecha Término&nbsp;&nbsp;</span>
        <span class="dt-val">{_fmt_date_display(fecha_termino)}</span>
      </p>
      <p class="grand-tot">{_fmt_clp(total_pagar)}</p>
    </td>
  </tr>
</table>

<!-- Glosa + totals: real table -->
<table class="glosa-table">
  <tr>
    <td colspan="3" class="glosa-title">GLOSA</td>
  </tr>
  <tr>
    <td colspan="3" class="glosa-body">{glosa}</td>
  </tr>
  <tr class="totals-row">
    <td class="tot-cell">
      <div class="tot-label">Total a Trato</div>
      <div class="tot-value">{_fmt_clp(total_trato)}</div>
    </td>
    <td class="tot-cell">
      <div class="tot-label">Total Al Día</div>
      <div class="tot-value">{_fmt_clp(total_al_dia)}</div>
    </td>
    <td class="tot-cell tot-cell-hl">
      <div class="tot-label">Total a Pagar</div>
      <div class="tot-value">{_fmt_clp(total_pagar)}</div>
    </td>
  </tr>
</table>

<p class="pivot-title">ORDEN DE FACTURACIÓN</p>
<table class="pivot-table">
  <thead>
    <tr>
      <th>Total Trabajador</th>
      {date_headers}
      <th class="num">Suma total</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
    {foot_html}
  </tbody>
</table>

</body></html>"""

    buf = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html), dest=buf)
    buf.seek(0)

    filename = (
        f"facturacion_{contratista.replace(' ', '_')}_{empresa.replace(' ', '_')}"
        f"_{fecha_inicio}_{fecha_termino}.pdf"
    )
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
