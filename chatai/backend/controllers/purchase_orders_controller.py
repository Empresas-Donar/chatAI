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
  GET  /api/odoo/facturacion/data         → Screen header + pivot (same source as PDF)
  GET  /api/odoo/facturacion/pdf          → PDF of billing order (opens in new tab)
  GET  /api/tarjas/cc-status              → CC sync status (archived IDs detection)
  POST /api/tarjas/sync-cc                → Trigger CC sync on demand
"""

import base64
import datetime
import decimal
import io
import json as _json
import logging
import os
import re
from pathlib import Path

import openpyxl
from xhtml2pdf import pisa
from google.cloud import bigquery
from google.oauth2 import service_account

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from auth import require_auth
from db import get_connection
from tarjas_empresa import total_empresa

logger = logging.getLogger("controllers.purchase_orders")


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


def _sync_labores(
    conn, fecha_inicio: str, fecha_termino: str, vendedor: str, nombre_campo: str
):
    """Find labores without a product code in the given period and auto-map from BigQuery."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT r."Nombre Labor"
            FROM appsheet.tarjas_reporte r
            WHERE r.fecha BETWEEN %s AND %s
              AND r.contratista = %s
              AND r.nombre_campo = %s
              AND COALESCE(
                  (SELECT l.codigo_labor FROM appsheet.tarjas_labores l
                   WHERE TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(l.labor), '\s+', ' ', 'g'), '\(\s+', '(', 'g'), '\s+\)', ')', 'g'))
                       = TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(LOWER(r."Nombre Labor"), '\s+', ' ', 'g'), '\(\s+', '(', 'g'), '\s+\)', ')', 'g'))
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
        """,
            (fecha_inicio, fecha_termino, vendedor, nombre_campo),
        )
        unmapped = [row[0] for row in cur.fetchall()]

    if not unmapped:
        return

    bq = _get_bq_client()
    placeholders = ", ".join(
        f"'{labor.replace(chr(39), chr(39) * 2)}'" for labor in unmapped
    )
    query = f"""
        SELECT
            TRIM(JSON_VALUE(p.name, '$.es_CL')) AS nombre,
            p.default_code                       AS codigo
        FROM `ace-scarab-484515-v1.odoo_data.Producto` p
        WHERE p.default_code IS NOT NULL
          AND TRIM(JSON_VALUE(p.name, '$.es_CL')) IN ({placeholders})
    """
    results = bq.query(query).result()
    matches = {row.nombre: row.codigo for row in results}

    if not matches:
        return

    with conn.cursor() as cur:
        for labor, codigo in matches.items():
            cur.execute(
                """
                INSERT INTO appsheet.tarjas_labores (codigo_labor, labor)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """,
                (codigo, labor),
            )
            logger.info(f"Auto-mapped labor: '{labor}' → {codigo}")
    conn.commit()


router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Exact tipo_pago values from the DB
_PAYMENT_TYPE_TRATO = "trato"
_PAYMENT_TYPE_AL_DIA = "Al dia"

# Billable amount for Orden de Facturación / tarjas_reporte.
# Domain formula (sql/tarjas/01_views_reporte.sql):
#   total_pagar = total_trabajado + total_contratista
# AppSheet has been leaving total_pagar at 0 on new rows since ~2026-08-24
# while still filling the parts (issue #156). Treat 0 as missing.
_BILLABLE_SQL = (
    "COALESCE(NULLIF(total_pagar, 0), "
    "COALESCE(total_trabajado, 0) + COALESCE(total_contratista, 0))"
)


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


def _purchase_order_lines(cur, contratista, empresa, fecha_inicio, fecha_termino):
    """OC lines from Aprobado tarjas_pagos, billed as Costo Empresa.

    Detalle, OC, facturación, Notas and the Odoo xlsx share
    tarjas_empresa.total_empresa (Trato +45 %, Al Día +50 % — never
    invert). Never bill from AppSheet total_pagar (often 0) or
    trabajado+comisión.
    """
    cur.execute(
        """
        SELECT
            tipo_pago,
            cuartel_cc AS "CC",
            labor AS "Nombre Labor",
            COUNT(*) AS jornadas,
            COALESCE(SUM(total_trabajado), 0) AS total_trabajado
        FROM appsheet.tarjas_pagos
        WHERE estado = 'Aprobado'
          AND contratista = %s
          AND nombre_campo = %s
          AND fecha::date BETWEEN %s AND %s
        GROUP BY tipo_pago, cuartel_cc, labor
        ORDER BY tipo_pago DESC, cuartel_cc, labor
        """,
        (contratista, empresa, fecha_inicio, fecha_termino),
    )
    columns = [d[0] for d in cur.description]
    rows = [
        {k: _serialize(v) for k, v in zip(columns, r)} for r in cur.fetchall()
    ]
    for r in rows:
        emp = float(total_empresa(r.get("tipo_pago"), r.get("total_trabajado")))
        jornadas = float(r.get("jornadas") or 0)
        r["contratista"] = contratista
        r["nombre_campo"] = empresa
        r["total_labor"] = emp
        r["total_unitario"] = round(emp / jornadas, 2) if jornadas else None
    grand = sum(float(r["total_labor"] or 0) for r in rows)
    for r in rows:
        amount = float(r["total_labor"] or 0)
        r["pct_pago"] = round(amount / grand * 100, 2) if grand else 0.0
    return rows


def _purchase_order_header(rows, fecha_inicio, fecha_termino):
    if not rows:
        return None
    total_trato = sum(
        r["total_labor"] or 0
        for r in rows
        if r.get("tipo_pago") == _PAYMENT_TYPE_TRATO
    )
    # Catch-all (not an exact "== _PAYMENT_TYPE_AL_DIA" match): tipo_pago
    # values other than "trato" (e.g. "Bono") still count toward the total,
    # so screen and PDF cannot drop rows (issue #88).
    total_al_dia = sum(
        r["total_labor"] or 0
        for r in rows
        if r.get("tipo_pago") != _PAYMENT_TYPE_TRATO
    )
    total_pagar = total_trato + total_al_dia
    pct_trato = round(total_trato / total_pagar * 100, 1) if total_pagar else 0
    pct_al_dia = round(total_al_dia / total_pagar * 100, 1) if total_pagar else 0
    return {
        "contractor": rows[0]["contratista"],
        "company": rows[0]["nombre_campo"],
        "date_from": fecha_inicio,
        "date_to": fecha_termino,
        "total_trato": total_trato,
        "total_al_dia": total_al_dia,
        "total": total_pagar,
        "pct_trato": pct_trato,
        "pct_al_dia": pct_al_dia,
    }


def _line_key(tipo_pago, cc, labor):
    return ((tipo_pago or "").strip(), str(cc or "").strip(), (labor or "").strip())


def _odoo_meta_by_line(cur, contratista, empresa, fecha_inicio, fecha_termino):
    """product_id / analytic from the Odoo view, keyed like OC lines."""
    cur.execute(
        """
        SELECT
            tipo_pago,
            "Lineas del pedido/Producto/Nombre" AS labor,
            "Lineas del pedido/Código de Distribución Analítica/Código" AS cc,
            MAX("order_line/product_id") AS product_id,
            MAX("order_line/analytic_distribution") AS analytic
        FROM appsheet.tarjas_reporte_odoo
        WHERE "Vendedor" = %s
          AND nombre_campo = %s
          AND fecha BETWEEN %s AND %s
        GROUP BY 1, 2, 3
        """,
        (contratista, empresa, fecha_inicio, fecha_termino),
    )
    meta = {}
    for tipo, labor, cc, product_id, analytic in cur.fetchall():
        meta[_line_key(tipo, cc, labor)] = (product_id, analytic)
    return meta


def costo_empresa_odoo_lines(cur, contratista, empresa, fecha_inicio, fecha_termino):
    """OC grain + Costo Empresa prices, with Odoo product_id / analytic.

    Changing tarjas_empresa factors changes Detalle, OC header, Facturación,
    Notas and this export in one place. The SQL view's pagar_efectivo price
    is mapping metadata only — never billed from.
    """
    oc_rows = _purchase_order_lines(
        cur, contratista, empresa, fecha_inicio, fecha_termino
    )
    meta = _odoo_meta_by_line(
        cur, contratista, empresa, fecha_inicio, fecha_termino
    )
    lines = []
    for r in oc_rows:
        key = _line_key(r.get("tipo_pago"), r.get("CC"), r.get("Nombre Labor"))
        product_id, analytic = meta.get(key, (None, None))
        lines.append(
            {
                "partner_id": contratista,
                "product_id": product_id,
                "analytic": analytic,
                "qty": float(r.get("jornadas") or 0),
                "price_unit": float(r.get("total_unitario") or 0),
                "total": float(r.get("total_labor") or 0),
                "tipo_pago": r.get("tipo_pago"),
                "cc": r.get("CC"),
                "labor": r.get("Nombre Labor"),
            }
        )
    return lines


def _analytic_has_empty_key(analytic) -> bool:
    if analytic is None:
        return True
    if isinstance(analytic, dict):
        return "" in analytic or not analytic
    return '"": ' in str(analytic) or str(analytic).strip() in ("", "{}", "–")


def group_odoo_export_rows(lines):
    """Group priced lines by product_id + analytic for the Odoo xlsx."""
    grouped: dict[tuple, dict] = {}
    excluded_amount = 0.0
    export_rows = []
    for line in lines:
        product_id = line.get("product_id")
        analytic = line.get("analytic")
        amount = float(line.get("total") or 0)
        if not product_id or _analytic_has_empty_key(analytic):
            excluded_amount += amount
            continue
        key = (line.get("partner_id"), product_id, analytic)
        g = grouped.setdefault(key, {"qty": 0.0, "amount": 0.0})
        g["qty"] += float(line.get("qty") or 0)
        g["amount"] += amount
    for (partner_id, product_id, analytic), g in sorted(
        grouped.items(), key=lambda item: str(item[0][1] or "")
    ):
        qty = g["qty"]
        price = round(g["amount"] / qty, 2) if qty else None
        export_rows.append((partner_id, product_id, qty, analytic, price))
    return export_rows, excluded_amount


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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )
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

    Amounts are Costo Empresa (total_trabajado × platform factor), the same
    as Detalle operacional — not AppSheet pagar_efectivo on tarjas_reporte.
    """
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    try:
        with conn.cursor() as cur:
            data = _purchase_order_lines(
                cur, contratista, empresa, fecha_inicio, fecha_termino
            )
    finally:
        conn.close()

    if not data:
        return {"rows": [], "header": None}

    return {
        "header": _purchase_order_header(data, fecha_inicio, fecha_termino),
        "rows": data,
    }


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
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    try:
        _sync_labores(conn, fecha_inicio, fecha_termino, contratista, empresa)
    except Exception as exc:
        logger.warning(f"Labor auto-sync failed (non-fatal): {exc}")

    try:
        with conn.cursor() as cur:
            priced = costo_empresa_odoo_lines(
                cur, contratista, empresa, fecha_inicio, fecha_termino
            )
            rows, excluded_amount = group_odoo_export_rows(priced)
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

_BQ_ALL_CC_QUERY = """
    SELECT
      CAST(id AS STRING) AS id,
      code,
      active,
      CAST(root_plan_id AS STRING) AS root_plan_id,
      COALESCE(
        JSON_VALUE(name, '$.es_CL'),
        JSON_VALUE(name, '$.en_US'),
        CAST(id AS STRING)
      ) AS nombre
    FROM `ace-scarab-484515-v1.odoo_data.CC_analiticos`
"""


@router.get("/api/tarjas/cc-status")
async def get_cc_status():
    """
    Compara los IDs almacenados en tarjas_cc.valor_odoo contra los CC activos en Odoo (BigQuery).
    Devuelve por cada CC si está ok, archivado o vacío, y la fecha de último sync.
    """
    # 1. Fetch ALL Odoo CC (active + archived) to detect stale IDs
    active_ids: set[str] | None = None
    odoo_names: dict[str, str] = {}  # id → nombre legible
    bq_available = False
    try:
        bq = _get_bq_client()
        bq_rows = list(bq.query(_BQ_ALL_CC_QUERY).result())
        active_ids = {r["id"] for r in bq_rows if r["active"]}
        odoo_names = {r["id"]: r["nombre"] for r in bq_rows}
        bq_available = True
    except Exception as exc:
        logger.warning(f"BigQuery no disponible para cc-status: {exc}")

    # 2. tarjas_cc and last sync time from PostgreSQL
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    cc_rows = []
    last_sync = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id_cc::text, cultivo, valor_odoo FROM appsheet.tarjas_cc ORDER BY id_cc"
            )
            cc_rows = cur.fetchall()

            try:
                cur.execute(
                    "SELECT value FROM appsheet.sync_meta WHERE key = 'last_cc_sync'"
                )
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

        archived_ids: list[str] = []
        if not stored_ids:
            status = "empty"
            empty_count += 1
        elif active_ids is None:
            status = "unknown"
            unknown_count += 1
        else:
            archived_ids = [sid for sid in stored_ids if sid not in active_ids]
            if archived_ids:
                status = "archived"
                archived_count += 1
            else:
                status = "ok"
                ok_count += 1

        # Resolve human-readable names for stored IDs
        stored_names = [odoo_names.get(sid, sid) for sid in stored_ids]

        result.append(
            {
                "id_cc": id_cc,
                "cultivo": cultivo,
                "stored_ids": stored_ids,
                "stored_names": stored_names,
                "archived_ids": archived_ids,
                "status": status,
            }
        )

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


@router.get("/api/tarjas/export-preview")
async def get_export_preview(
    contratista: str,
    empresa: str,
    fecha_inicio: str,
    fecha_termino: str,
):
    """
    Vista previa de lo que se exportará a Odoo:
    - Filas válidas (product_id mapeado + CC activo) → se incluyen en el xlsx
    - Filas excluidas (sin labor o CC vacío/archivado) → se omiten con motivo
    Para cada CC resuelve el nombre legible desde BigQuery.
    """
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    # 1. Fetch active CC names from BigQuery (best-effort)
    active_ids: set[str] = set()
    odoo_names: dict[str, str] = {}
    bq_available = False
    try:
        bq = _get_bq_client()
        bq_rows = list(bq.query(_BQ_ALL_CC_QUERY).result())
        active_ids = {r["id"] for r in bq_rows if r["active"]}
        odoo_names = {r["id"]: r["nombre"] for r in bq_rows}
        bq_available = True
    except Exception as exc:
        logger.warning(f"BigQuery no disponible en export-preview: {exc}")

    # 2. Query individual export rows from PG (no GROUP BY — one row per line)
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    last_sync = None
    try:
        with conn.cursor() as cur:
            priced = costo_empresa_odoo_lines(
                cur, contratista, empresa, fecha_inicio, fecha_termino
            )
            try:
                cur.execute(
                    "SELECT value FROM appsheet.sync_meta WHERE key = 'last_cc_sync'"
                )
                meta = cur.fetchone()
                last_sync = meta[0] if meta else None
            except Exception:
                pass
    finally:
        conn.close()

    # 3. Classify each Costo Empresa line (same grain as the OC document)
    preview_rows = []
    excluded_rows = []
    total_ok = 0.0
    total_excluded = 0.0

    for line in priced:
        product_id = line.get("product_id")
        analytic = line.get("analytic")
        qty_f = float(line.get("qty") or 0)
        price_f = float(line.get("price_unit") or 0)
        total_line = round(float(line.get("total") or 0), 0)

        # Parse analytic distribution into dict
        analytic_dict: dict = {}
        if isinstance(analytic, dict):
            analytic_dict = analytic
        elif isinstance(analytic, str):
            try:
                analytic_dict = _json.loads(analytic)
            except Exception:
                pass

        cc_ids = [k for k in analytic_dict.keys() if k != ""]
        cc_display = _cc_display(analytic_dict, odoo_names)

        if not product_id:
            excluded_rows.append(
                {
                    "product_id": "–",
                    "cc_display": cc_display,
                    "qty": qty_f,
                    "price_unit": price_f,
                    "total": total_line,
                    "reason": "Labor sin mapear en Odoo",
                }
            )
            total_excluded += total_line
            continue

        if not cc_ids:
            excluded_rows.append(
                {
                    "product_id": product_id,
                    "cc_display": "–",
                    "qty": qty_f,
                    "price_unit": price_f,
                    "total": total_line,
                    "reason": "CC vacío o sin mapear",
                }
            )
            total_excluded += total_line
            continue

        archived = [cid for cid in cc_ids if bq_available and cid not in active_ids]

        analytic_str = (
            _json.dumps(analytic_dict, ensure_ascii=False) if analytic_dict else "–"
        )

        if archived:
            excluded_rows.append(
                {
                    "product_id": product_id,
                    "analytic_distribution": analytic_str,
                    "cc_display": cc_display,
                    "archived_ids": archived,
                    "qty": qty_f,
                    "price_unit": price_f,
                    "total": total_line,
                    "reason": f"CC archivado: {', '.join(odoo_names.get(a, a) for a in archived)}",
                }
            )
            total_excluded += total_line
        else:
            preview_rows.append(
                {
                    "product_id": product_id,
                    "analytic_distribution": analytic_str,
                    "cc_display": cc_display,
                    "qty": qty_f,
                    "price_unit": price_f,
                    "total": total_line,
                }
            )
            total_ok += total_line

    return {
        "rows": preview_rows,
        "excluded": excluded_rows,
        "total_ok": total_ok,
        "total_excluded": total_excluded,
        "rows_count": len(preview_rows),
        "excluded_count": len(excluded_rows),
        "bq_available": bq_available,
        "last_sync": last_sync,
    }


def _cc_display(analytic: dict | None, odoo_names: dict[str, str]) -> str:
    """Return human-readable CC distribution string, e.g. 'CEREZOS LAPINS (50%) / CEREZOS SANTINA (50%)'."""
    if not analytic:
        return "–"
    parts = []
    multi = len([k for k in analytic if k != ""]) > 1
    for cid, pct in analytic.items():
        if cid == "":
            continue
        name = odoo_names.get(cid, cid)
        parts.append(f"{name} ({float(pct):.0f}%)" if multi else name)
    return " / ".join(parts) if parts else "–"


def _build_replacements_map(bq_rows: list) -> dict[str, list[tuple[str, float]]]:
    """
    Build archived_id → [(replacement_id, fraction), ...] map.

    Strategy (in order):
    1. Direct code match: archived CC has same code as an active CC → 1:1 replacement
    2. Name-prefix siblings in same root_plan: archived name stripped of ' CC-NNN' suffix
       matches the start of N active CCs in the same plan → split evenly (1/N each)
    """
    by_code: dict[str, str] = {}  # code → active_id
    by_plan: dict[str, list[dict]] = {}  # root_plan_id → list of all rows
    active_ids: set[str] = set()

    for r in bq_rows:
        oid = str(r["id"])
        code = str(r["code"]).strip() if r["code"] else None
        plan = str(r["root_plan_id"]) if r.get("root_plan_id") else None

        if r["active"]:
            active_ids.add(oid)
            if code and code not in by_code:
                by_code[code] = oid

        if plan:
            by_plan.setdefault(plan, []).append(
                {
                    "id": oid,
                    "code": code,
                    "active": r["active"],
                    "nombre": r["nombre"] or "",
                    "root_plan_id": plan,
                }
            )

    _dir_suffix = re.compile(r"[-\s]*(NORTE|SUR|ORIENTE|PONIENTE)\s*$", re.IGNORECASE)

    def _stem(name: str) -> str:
        return _dir_suffix.sub("", name).strip()

    def _lev(a: str, b: str) -> int:
        a, b = a.lower(), b.lower()
        if len(a) > len(b):
            a, b = b, a
        curr = list(range(len(a) + 1))
        for cb in b:
            prev = curr[:]
            curr[0] = prev[0] + 1
            for i, ca in enumerate(a):
                curr[i + 1] = (
                    prev[i] if ca == cb else 1 + min(prev[i], prev[i + 1], curr[i])
                )
        return curr[len(a)]

    def _matches(base: str, stem: str) -> bool:
        b, s = base.lower(), stem.lower()
        if s.startswith(b):
            return True
        if _lev(b, s) <= 1:
            return re.findall(r"\d+", b) == re.findall(r"\d+", s)
        return False

    replacements: dict[str, list[tuple[str, float]]] = {}
    for r in bq_rows:
        oid = str(r["id"])
        if r["active"]:
            continue

        code = str(r["code"]).strip() if r["code"] else None

        # Strategy 1: direct code replacement
        if code and code in by_code:
            replacements[oid] = [(by_code[code], 1.0)]
            continue

        # Strategy 2: fuzzy name siblings in same plan (handles splits + typos in Odoo)
        nombre = r["nombre"] or ""
        base = re.sub(r"\s+CC-\d+\s*$", "", nombre, flags=re.IGNORECASE).strip()
        plan = str(r.get("root_plan_id") or "")

        if base and plan:
            siblings = [
                s
                for s in by_plan.get(plan, [])
                if s["active"] and _matches(base, _stem(s["nombre"]))
            ]
            if siblings:
                fraction = 1.0 / len(siblings)
                replacements[oid] = [(s["id"], fraction) for s in siblings]

    return replacements


@router.post("/api/tarjas/sync-cc")
async def trigger_cc_sync():
    """
    Sincroniza tarjas_cc.valor_odoo contra los CC activos en Odoo (BigQuery).
    Detecta IDs archivados y los reemplaza por sus equivalentes activos:
    - 1:1 si tienen mismo código en Odoo
    - 1:N si el CC fue dividido (ej. CC-421 → ORIENTE + PONIENTE), repartiendo el % equitativamente
    """
    # 1. Fetch ALL CC (active + archived) from BigQuery
    try:
        bq = _get_bq_client()
        bq_rows = list(bq.query(_BQ_ALL_CC_QUERY).result())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"BigQuery no disponible: {exc}")

    active_ids = {str(r["id"]) for r in bq_rows if r["active"]}
    archived_to_replacements = _build_replacements_map(bq_rows)

    # For filling empty mappings (by code)
    by_code: dict[str, str] = {}
    for r in bq_rows:
        if r["active"] and r["code"] and str(r["code"]).strip() not in by_code:
            by_code[str(r["code"]).strip()] = str(r["id"])

    # 2. Fetch current tarjas_cc
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    fixed = 0
    now_iso = datetime.datetime.utcnow().isoformat()

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id_cc::text, valor_odoo FROM appsheet.tarjas_cc")
            existing = cur.fetchall()

        to_fix: list[tuple[str, str]] = []
        for id_cc, valor_odoo in existing:
            stored: dict = valor_odoo if isinstance(valor_odoo, dict) else {}
            if isinstance(valor_odoo, str):
                try:
                    stored = _json.loads(valor_odoo)
                except Exception:
                    stored = {}

            stored_keys = [k for k in stored.keys() if k != ""]
            code = str(id_cc).strip()

            if not stored_keys or list(stored.keys()) == [""]:
                # Empty → fill with active ID if code is known
                if code in by_code:
                    to_fix.append((_json.dumps({by_code[code]: 100}), id_cc))
            else:
                # Replace archived IDs; support 1:N splits (pct divided evenly)
                updated: dict[str, float] = {}
                changed = False
                for kid, pct in stored.items():
                    if kid == "":
                        continue
                    if kid not in active_ids and kid in archived_to_replacements:
                        for repl_id, fraction in archived_to_replacements[kid]:
                            updated[repl_id] = round(
                                updated.get(repl_id, 0) + pct * fraction, 4
                            )
                        changed = True
                    else:
                        updated[kid] = pct
                if changed:
                    to_fix.append((_json.dumps(updated), id_cc))

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
            cur.execute(
                """
                INSERT INTO appsheet.sync_meta (key, value) VALUES ('last_cc_sync', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
                (now_iso,),
            )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error en sincronización: {exc}")
    finally:
        conn.close()

    return {
        "fixed": fixed,
        "synced_at": now_iso,
        "message": f"Sync completado: {fixed} CC actualizados con IDs vigentes.",
    }


# ---------------------------------------------------------------------------
# Billing order PDF
# ---------------------------------------------------------------------------


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
@page { size: A4 landscape; margin: 12mm 14mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 8pt; color: #111; margin: 0; }

/* ── Header uses real <table> for xhtml2pdf compat ── */
.hdr-table { width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1;
             margin-bottom: 10px; }
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
.tot-cell-5  { width: 20%; }
.tot-cell-hl { background: #fef08a; }
.tot-label   { font-size: 7pt; font-weight: 700; color: #64748b; text-transform: uppercase; }
.tot-value   { font-size: 13pt; font-weight: 800; color: #1e293b; margin-top: 2px; }
.tot-cell-5 .tot-value { font-size: 11pt; }
.tot-pct     { font-size: 8pt; font-weight: 700; color: #64748b; margin-top: 1px; }

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

.summary-table { width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1;
                 margin-top: 8px; }
.summary-table td { text-align: center; padding: 8px 6px; width: 33%;
                    border-right: 1px solid #e2e8f0; }

/* ── Detail table (OC / notas print) ── */
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


def _pct(part, base):
    """Commission or share as percent; None when the base is 0."""
    if not base:
        return None
    return round(100.0 * float(part) / float(base), 1)


def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    text = f"{float(v):.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") + "%"


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


def _tipo_badges_html(tipos) -> str:
    """Compact Trato / Al día marks for the worker column."""
    seen: set[str] = set()
    parts: list[str] = []
    for raw in tipos:
        t = (raw or "").strip()
        if not t:
            continue
        is_trato = t.lower() == _PAYMENT_TYPE_TRATO
        key = "trato" if is_trato else "aldia"
        if key in seen:
            continue
        seen.add(key)
        if is_trato:
            parts.append('<span class="badge-trato">Trato</span>')
        elif t.lower() in ("al dia", "al día"):
            parts.append('<span class="badge-aldia">Al día</span>')
        else:
            parts.append(f'<span class="badge-aldia">{t}</span>')
    return " ".join(parts)


def _fmt_date_short(iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(iso)
        return f"{d.day}/{d.month}"
    except Exception:
        return iso


def _billing_costo_parts(tipo_pago, total_trabajado):
    """Costo Empresa, trabajadores, adicional — same factors as Detalle/OC."""
    trab = float(total_trabajado or 0)
    emp = float(total_empresa(tipo_pago, trab))
    return emp, trab, emp - trab


def _fetch_billing_order(conn, contratista, empresa, fecha_inicio, fecha_termino):
    """Header totals + worker×date pivot from one snapshot of tarjas_pagos.

    Same scope as Detalle (estado='Aprobado'). Billable amount is Costo
    Empresa via total_empresa() (Trato +45 %, Al Día +50 % — never
    invert), not AppSheet total_pagar or trabajado+comisión.

    Pivot columns stay positional: (trabajador, fecha, total_pagar, …)
    so existing tests that read r[2] as the billed amount keep working.
    total_trabajado / total_contratista are the worker pay and adicional.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tipo_pago,
                   SUM(COALESCE(total_trabajado, 0)) AS total_trabajado
            FROM appsheet.tarjas_pagos
            WHERE contratista  = %s
              AND nombre_campo = %s
              AND estado       = 'Aprobado'
              AND fecha::date BETWEEN %s AND %s
            GROUP BY tipo_pago
            """,
            (contratista, empresa, fecha_inicio, fecha_termino),
        )
        tipo_rows = [
            (tipo,) + _billing_costo_parts(tipo, trab)
            for tipo, trab in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT trabajador, fecha::date::text AS fecha, tipo_pago,
                   SUM(COALESCE(total_trabajado, 0)) AS total_trabajado
            FROM appsheet.tarjas_pagos
            WHERE contratista  = %s
              AND nombre_campo = %s
              AND estado       = 'Aprobado'
              AND fecha::date BETWEEN %s AND %s
            GROUP BY trabajador, fecha::date, tipo_pago
            ORDER BY trabajador, fecha::date, tipo_pago
            """,
            (contratista, empresa, fecha_inicio, fecha_termino),
        )
        pivot_rows = []
        for trabajador, fecha, tipo, trab in cur.fetchall():
            emp, trab_f, com = _billing_costo_parts(tipo, trab)
            pivot_rows.append((trabajador, fecha, emp, trab_f, com, tipo))
    return tipo_rows, pivot_rows


def _billing_header_from_tipo_rows(
    tipo_rows, contratista, empresa, fecha_inicio, fecha_termino
):
    total_trato = sum(
        float(r[1] or 0) for r in tipo_rows if r[0] == _PAYMENT_TYPE_TRATO
    )
    total_al_dia = sum(
        float(r[1] or 0) for r in tipo_rows if r[0] != _PAYMENT_TYPE_TRATO
    )
    total_pagar = total_trato + total_al_dia
    total_trabajado = sum(
        float(r[2] or 0) for r in tipo_rows if len(r) > 2
    )
    total_contratista = sum(
        float(r[3] or 0) for r in tipo_rows if len(r) > 3
    )
    trab_trato = sum(
        float(r[2] or 0)
        for r in tipo_rows
        if r[0] == _PAYMENT_TYPE_TRATO and len(r) > 2
    )
    com_trato = sum(
        float(r[3] or 0)
        for r in tipo_rows
        if r[0] == _PAYMENT_TYPE_TRATO and len(r) > 3
    )
    trab_al_dia = sum(
        float(r[2] or 0)
        for r in tipo_rows
        if r[0] != _PAYMENT_TYPE_TRATO and len(r) > 2
    )
    com_al_dia = sum(
        float(r[3] or 0)
        for r in tipo_rows
        if r[0] != _PAYMENT_TYPE_TRATO and len(r) > 3
    )
    if not tipo_rows and total_pagar == 0:
        return None
    pct_trato = round(total_trato / total_pagar * 100, 1) if total_pagar else 0
    pct_al_dia = round(total_al_dia / total_pagar * 100, 1) if total_pagar else 0
    return {
        "contractor": contratista,
        "company": empresa,
        "date_from": fecha_inicio,
        "date_to": fecha_termino,
        "total_trato": total_trato,
        "total_al_dia": total_al_dia,
        "total": total_pagar,
        "total_trabajado": total_trabajado,
        "total_contratista": total_contratista,
        "pct_trato": pct_trato,
        "pct_al_dia": pct_al_dia,
        "pct_trabajadores": _pct(total_trabajado, total_pagar),
        "pct_comision": _pct(total_contratista, total_trabajado),
        "pct_comision_trato": _pct(com_trato, trab_trato),
        "pct_comision_al_dia": _pct(com_al_dia, trab_al_dia),
    }


@router.get("/api/odoo/facturacion/data")
async def billing_order_data(
    contratista: str,
    empresa: str,
    fecha_inicio: str,
    fecha_termino: str,
):
    """Screen payload for Orden de Facturación: header + pivot from one source.

    Replaces the previous split of GET /api/purchase-orders (header, view,
    total_pagar) + GET /api/tarjas/contratista (pivot, unfiltered,
    total_trabajado) that made the two blocks on the same page disagree
    (issue #156). Does not change /api/tarjas/contratista.
    """
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    try:
        tipo_rows, pivot_rows = _fetch_billing_order(
            conn, contratista, empresa, fecha_inicio, fecha_termino
        )
    finally:
        conn.close()

    header = _billing_header_from_tipo_rows(
        tipo_rows, contratista, empresa, fecha_inicio, fecha_termino
    )
    rows = [
        {
            "trabajador": r[0],
            "fecha": r[1],
            "total_pagar": _serialize(r[2]),
            "total_trabajado": _serialize(r[3]),
            "total_contratista": _serialize(r[4]),
            "tipo_pago": r[5] if len(r) > 5 else None,
        }
        for r in pivot_rows
    ]
    return {
        "header": header,
        "columns": [
            "trabajador",
            "fecha",
            "total_pagar",
            "total_trabajado",
            "total_contratista",
            "tipo_pago",
        ],
        "rows": rows,
        "count": len(rows),
    }


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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    try:
        tipo_rows, pivot_rows = _fetch_billing_order(
            conn, contratista, empresa, fecha_inicio, fecha_termino
        )
    finally:
        conn.close()

    header = _billing_header_from_tipo_rows(
        tipo_rows, contratista, empresa, fecha_inicio, fecha_termino
    )
    total_trato = header["total_trato"] if header else 0
    total_al_dia = header["total_al_dia"] if header else 0
    total_pagar = header["total"] if header else 0
    total_trabajado = header["total_trabajado"] if header else 0
    total_contratista = header["total_contratista"] if header else 0
    pct_comision = header.get("pct_comision") if header else None
    pct_comision_trato = header.get("pct_comision_trato") if header else None
    pct_comision_al_dia = header.get("pct_comision_al_dia") if header else None

    # Build pivot structure: date → {total, trabajado, comision}
    dates: list[str] = sorted({r[1] for r in pivot_rows if r[1]})
    workers: dict[str, dict] = {}
    worker_tipos: dict[str, set[str]] = {}
    for row in pivot_rows:
        w = row[0] or "(sin nombre)"
        fecha = row[1]
        if w not in workers:
            workers[w] = {}
            worker_tipos[w] = set()
        prev = workers[w].get(fecha, {"total": 0.0, "trabajado": 0.0, "comision": 0.0})
        workers[w][fecha] = {
            "total": prev["total"] + float(row[2] or 0),
            "trabajado": prev["trabajado"] + float(row[3] or 0),
            "comision": prev["comision"] + float(row[4] or 0),
        }
        if len(row) > 5 and row[5]:
            worker_tipos[w].update(t.strip() for t in str(row[5]).split(",") if t.strip())

    sorted_workers = sorted(workers.items())

    def _empty_cell():
        return {"total": 0.0, "trabajado": 0.0, "comision": 0.0}

    col_totals = {
        d: {
            "total": sum(wdata.get(d, _empty_cell())["total"] for _, wdata in sorted_workers),
            "trabajado": sum(
                wdata.get(d, _empty_cell())["trabajado"] for _, wdata in sorted_workers
            ),
            "comision": sum(
                wdata.get(d, _empty_cell())["comision"] for _, wdata in sorted_workers
            ),
        }
        for d in dates
    }
    grand_trabajado = sum(c["trabajado"] for c in col_totals.values())

    # ── HTML ──
    d1 = _fmt_date_display(fecha_inicio)
    d2 = _fmt_date_display(fecha_termino)
    glosa = f"SERVICIOS DE LABORES AGRÍCOLAS {d1.upper()} AL {d2.upper()}"
    semana = f"Semana desde {d1} al {d2}"

    date_headers = "".join(f'<th class="num">{_fmt_date_short(d)}</th>' for d in dates)

    rows_html = ""
    for worker, wdata in sorted_workers:
        row_trabajado = sum(wdata.get(d, _empty_cell())["trabajado"] for d in dates)
        cells = ""
        for d in dates:
            cell = wdata.get(d)
            v = cell["trabajado"] if cell else 0
            cells += f'<td class="num">{_fmt_clp(v) if v else "-"}</td>'
        even_cls = "even" if len(rows_html) % 2 == 0 else ""
        badges = _tipo_badges_html(worker_tipos.get(worker, set()))
        name_cell = f"{worker} {badges}".strip() if badges else worker
        rows_html += (
            f'<tr class="{even_cls}"><td>{name_cell}</td>{cells}'
            f'<td class="tot">{_fmt_clp(row_trabajado)}</td></tr>'
        )

    foot_cells = "".join(
        f"<td>{_fmt_clp(col_totals[d]['trabajado']) if col_totals[d]['trabajado'] else '-'}</td>"
        for d in dates
    )
    foot_html = (
        f'<tr class="foot"><td>Subtotal</td>{foot_cells}'
        f"<td>{_fmt_clp(grand_trabajado)}</td></tr>"
    )

    logo = _logo_b64()
    logo_html = (
        f'<img src="data:image/png;base64,{logo}" class="hdr-logo-img" />'
        if logo
        else "EMPRESAS DONAR"
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Orden de Facturación — {contratista}</title>
<style>{_PDF_CSS}</style>
</head><body>

<!-- Header: 3 columns using real table -->
<table class="hdr-table">
  <tr>
    <td class="hdr-logo">
      {logo_html}
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
    <td colspan="5" class="glosa-title">GLOSA</td>
  </tr>
  <tr>
    <td colspan="5" class="glosa-body">{glosa}</td>
  </tr>
  <tr class="totals-row">
    <td class="tot-cell tot-cell-5">
      <div class="tot-label">Total trabajadores</div>
      <div class="tot-value">{_fmt_clp(total_trabajado)}</div>
    </td>
    <td class="tot-cell tot-cell-5">
      <div class="tot-label">Adicional</div>
      <div class="tot-value">{_fmt_clp(total_contratista)}</div>
      <div class="tot-pct">{_fmt_pct(pct_comision)}</div>
    </td>
    <td class="tot-cell tot-cell-5">
      <div class="tot-label">Total a Trato</div>
      <div class="tot-value">{_fmt_clp(total_trato)}</div>
      <div class="tot-pct">{_fmt_pct(pct_comision_trato)}</div>
    </td>
    <td class="tot-cell tot-cell-5">
      <div class="tot-label">Total Al Día</div>
      <div class="tot-value">{_fmt_clp(total_al_dia)}</div>
      <div class="tot-pct">{_fmt_pct(pct_comision_al_dia)}</div>
    </td>
    <td class="tot-cell tot-cell-5 tot-cell-hl">
      <div class="tot-label">Total a Pagar</div>
      <div class="tot-value">{_fmt_clp(total_pagar)}</div>
    </td>
  </tr>
</table>

<p class="pivot-title">ORDEN DE FACTURACIÓN</p>
<table class="pivot-table">
  <thead>
    <tr>
      <th>Trabajador</th>
      {date_headers}
      <th class="num">Suma</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
    {foot_html}
  </tbody>
</table>

<table class="summary-table">
  <tr class="totals-row">
    <td class="tot-cell">
      <div class="tot-label">Subtotal</div>
      <div class="tot-value">{_fmt_clp(grand_trabajado)}</div>
    </td>
    <td class="tot-cell">
      <div class="tot-label">Adicional</div>
      <div class="tot-value">{_fmt_clp(total_contratista)}</div>
      <div class="tot-pct">{_fmt_pct(pct_comision)}</div>
    </td>
    <td class="tot-cell tot-cell-hl">
      <div class="tot-label">Total</div>
      <div class="tot-value">{_fmt_clp(total_pagar)}</div>
    </td>
  </tr>
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


# ---------------------------------------------------------------------------
# OC document print-PDF  (opens in new tab, same layout as the web page)
# ---------------------------------------------------------------------------


@router.get("/api/purchase-orders/print-pdf")
async def purchase_order_print_pdf(
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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    try:
        with conn.cursor() as cur:
            rows = _purchase_order_lines(
                cur, contratista, empresa, fecha_inicio, fecha_termino
            )
    finally:
        conn.close()

    if not rows:
        raise HTTPException(
            status_code=404, detail="Sin datos para los filtros indicados"
        )

    header = _purchase_order_header(rows, fecha_inicio, fecha_termino)
    total_trato = header["total_trato"]
    total_al_dia = header["total_al_dia"]
    total_pagar = header["total"]

    d1 = _fmt_date_display(fecha_inicio)
    d2 = _fmt_date_display(fecha_termino)
    glosa = f"SERVICIOS DE LABORES AGRÍCOLAS {d1.upper()} AL {d2.upper()}"
    semana = f"Semana desde {d1} al {d2}"

    rows_html = ""
    for i, r in enumerate(rows):
        tipo = r.get("tipo_pago")
        is_trato = (tipo or "").lower().strip() in ("trato", "a trato")
        tipo_label = "Trato" if is_trato else "Al día"
        tipo_cls = "badge-trato" if is_trato else "badge-aldia"
        even_cls = "even" if i % 2 == 0 else ""
        jornadas = r.get("jornadas")
        rows_html += f"""<tr class="{even_cls}">
          <td><span class="{tipo_cls}">{tipo_label}</span></td>
          <td>{r.get("CC") or ""}</td>
          <td>{r.get("Nombre Labor") or ""}</td>
          <td class="num">{int(jornadas) if jornadas is not None else "–"}</td>
          <td class="num">{_fmt_clp(r.get("total_unitario"))}</td>
          <td class="num">{_fmt_clp(r.get("total_labor"))}</td>
        </tr>"""

    logo = _logo_b64()
    logo_html = (
        f'<img src="data:image/png;base64,{logo}" class="hdr-logo-img" />'
        if logo
        else "EMPRESAS DONAR"
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Orden de Compra — {contratista}</title>
<style>{_PDF_CSS}</style>
</head><body>

<table class="hdr-table">
  <tr>
    <td class="hdr-logo">{logo_html}</td>
    <td class="hdr-mid">
      <p class="co-name">AGRÍCOLA DONAR — {empresa.upper()}</p>
      <p class="co-sub">Contratista: {contratista}</p>
      <p class="co-week">{semana}</p>
    </td>
    <td class="hdr-right">
      <p class="dt-row"><span class="dt-label">Fecha Inicio&nbsp;&nbsp;</span>
        <span class="dt-val">{d1}</span></p>
      <p class="dt-row"><span class="dt-label">Fecha Término&nbsp;&nbsp;</span>
        <span class="dt-val">{d2}</span></p>
      <p class="grand-tot">{_fmt_clp(total_pagar)}</p>
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
      <div class="tot-value">{_fmt_clp(total_al_dia)}</div></td>
    <td class="tot-cell tot-cell-hl"><div class="tot-label">Total a Pagar</div>
      <div class="tot-value">{_fmt_clp(total_pagar)}</div></td>
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
        f"oc_{contratista.replace(' ', '_')}_{empresa.replace(' ', '_')}"
        f"_{fecha_inicio}_{fecha_termino}.pdf"
    )
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
