"""
controllers/reports_controller.py
----------------------------------
Bulk PDF download page — lets users select multiple reports and download
them as a single merged PDF.

Routes:
  GET  /reportes                     → Report selection page
  GET  /api/reportes/bulk-pdf        → Generates and returns merged PDF
"""

import base64
import datetime
import decimal
import io
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from xhtml2pdf import pisa

from auth import require_auth
from db import get_connection

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TRACTORISTA_SQL = "(LOWER(TRIM(tipo_pago)) = 'tractorista')"
_TRACTORISTA_PAGOS_SQL = "(LOWER(TRIM(tipo_pago)) = 'tractorista')"

AVAILABLE_REPORTS = [
    {
        "id": "general",
        "label": "General operacional",
        "description": "Ganancia promedio por labor y ranking por persona",
        "category": "Tarjas — Contratistas",
    },
    {
        "id": "detalle",
        "label": "Detalle operacional",
        "description": "Desglose por labor, CC, jornadas y costo",
        "category": "Tarjas — Contratistas",
    },
    {
        "id": "contratista",
        "label": "Por persona operacional",
        "description": "Detalle diario por trabajador y contratista",
        "category": "Tarjas — Contratistas",
    },
    {
        "id": "resumen-persona",
        "label": "Resumen por persona",
        "description": "Pivot de pagos diarios por trabajador",
        "category": "Tarjas — Contratistas",
    },
    {
        "id": "resumen-horas",
        "label": "Horas extra por persona",
        "description": "Pivot de horas extra diarias por trabajador",
        "category": "Tarjas — Contratistas",
    },
    {
        "id": "detalle-tractorista",
        "label": "Detalle tractorista",
        "description": "Desglose por labor y CC (tractoristas)",
        "category": "Tarjas — Tractoristas",
    },
    {
        "id": "general-tractorista",
        "label": "General tractorista",
        "description": "Ganancia promedio por labor y ranking (tractoristas)",
        "category": "Tarjas — Tractoristas",
    },
    {
        "id": "resumen-tractorista",
        "label": "Resumen tractorista",
        "description": "Pivot de pagos diarios por tractorista",
        "category": "Tarjas — Tractoristas",
    },
]


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


# ── Shared PDF utilities ──────────────────────────────────────────────────────

def _serialize(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return str(v)
    return v


def _rows_to_dicts(cur):
    cols = [d[0] for d in cur.description]
    return [{k: _serialize(v) for k, v in zip(cols, r)} for r in cur.fetchall()]


def _logo_b64() -> str:
    path = Path(__file__).parent.parent.parent / "frontend" / "static" / "img" / "donar_logo.png"
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except OSError:
        return ""


def _fmt_clp(v) -> str:
    try:
        return f"${int(float(v or 0)):,}".replace(",", ".")
    except Exception:
        return "—"


def _fmt_date_display(iso: str) -> str:
    """Format an ISO date string (YYYY-MM-DD) as DD/MM/YYYY for user-facing display."""
    try:
        d = datetime.date.fromisoformat(iso)
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    except Exception:
        return iso


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
.page-break { page-break-before: always; }
.report-divider { border: none; border-top: 2px solid #333333; margin: 16px 0 12px 0; }
.pivot-table { table-layout: fixed; width: 100%; }
.pivot-table th { font-size: 6.5pt; padding: 4px 3px; }
.pivot-table td { font-size: 6.5pt; padding: 3px 3px; }
.pivot-table .col-worker { width: 18%; }
.pivot-table .col-tipo   { width: 9%; }
.pivot-table .col-total  { width: 10%; text-align: right; font-weight: bold; border-left: 1.5px solid #888888; }
"""


def _pdf_header(title: str, fecha_inicio: str, fecha_termino: str, empresa: str | None) -> str:
    now = datetime.date.today().strftime("%-d de %B de %Y")
    logo = _logo_b64()
    logo_cell = (
        f'<td style="border:none;width:90px;padding:4px 8px;background:#1e293b;vertical-align:middle">'
        f'<img src="data:image/png;base64,{logo}" style="width:80px;height:auto" /></td>'
    ) if logo else ""
    empresa_chip = f'<span class="chip"><b>Empresa:</b> {empresa}</span>' if empresa else ""
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
      <span class="chip"><b>Desde:</b> {_fmt_date_display(fecha_inicio)}</span>
      <span class="chip"><b>Hasta:</b> {_fmt_date_display(fecha_termino)}</span>
      {empresa_chip}
    </div>
    """


# ── SQL helpers ───────────────────────────────────────────────────────────────

_HORAS_EXPR = """NULLIF(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\.[0-9]+)?$'
                           THEN horas_trabajadas::numeric ELSE 0 END), 0)"""
_HORAS_SUM  = """COALESCE(SUM(CASE WHEN horas_trabajadas ~ '^[0-9]+(\.[0-9]+)?$'
                           THEN horas_trabajadas::numeric ELSE 0 END), 0)"""


def _base_where_pagos(fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None):
    filters = ["fecha::date BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(empresa)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    return "WHERE " + " AND ".join(filters), params


def _base_where_reporte(fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None):
    filters = ["fecha BETWEEN %s AND %s"]
    params: list = [fecha_inicio, fecha_termino]
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(empresa)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    return "WHERE " + " AND ".join(filters), params


# ── HTML generators per report ────────────────────────────────────────────────

def _html_general(cur, fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None) -> str:
    where, params = _base_where_pagos(fecha_inicio, fecha_termino, empresa, contratista)
    cur.execute(f"""
        SELECT labor,
               ROUND(AVG(total_trabajado)::numeric, 0)                     AS promedio_diario,
               ROUND(SUM(total_trabajado)::numeric / {_HORAS_EXPR}, 0)     AS ganancia_hora,
               ROUND(({_HORAS_SUM})::numeric, 1)                           AS total_horas,
               COALESCE(SUM(total_trabajado), 0)                           AS total
        FROM appsheet.tarjas_pagos {where}
        GROUP BY labor ORDER BY total DESC
    """, params)
    labor_rows = _rows_to_dicts(cur)

    cur.execute(f"""
        SELECT trabajador, contratista,
               ROUND(AVG(total_trabajado)::numeric, 0)                     AS promedio_diario,
               ROUND(SUM(total_trabajado)::numeric / {_HORAS_EXPR}, 0)     AS ganancia_hora,
               ROUND(({_HORAS_SUM})::numeric, 1)                           AS total_horas,
               COALESCE(SUM(total_trabajado), 0)                           AS total
        FROM appsheet.tarjas_pagos {where}
        GROUP BY trabajador, contratista ORDER BY total DESC
    """, params)
    ranking_rows = _rows_to_dicts(cur)

    fmtCLP = lambda v: _fmt_clp(v)
    fmtHrs = lambda v: f"{float(v):,.1f} h".replace(",", ".") if v else "—"

    labor_html = "".join(
        f'<tr><td>{r["labor"]}</td>'
        f'<td class="num">{fmtCLP(r["promedio_diario"])}</td>'
        f'<td class="num">{fmtCLP(r["ganancia_hora"])}</td>'
        f'<td class="num">{fmtHrs(r["total_horas"])}</td>'
        f'<td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in labor_rows
    )
    ranking_html = "".join(
        f'<tr><td>{r["trabajador"]}</td><td>{r["contratista"]}</td>'
        f'<td class="num">{fmtCLP(r["promedio_diario"])}</td>'
        f'<td class="num">{fmtCLP(r["ganancia_hora"])}</td>'
        f'<td class="num">{fmtHrs(r["total_horas"])}</td>'
        f'<td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in ranking_rows
    )
    header = _pdf_header("General — Tarjas Contratistas", fecha_inicio, fecha_termino, empresa)
    return f"""
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
    """


def _html_detalle(cur, fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None) -> str:
    where, params = _base_where_reporte(fecha_inicio, fecha_termino, empresa, contratista)
    cur.execute(f"""
        SELECT tipo_pago, "Nombre Labor" AS labor, "CC" AS centro_costo,
               SUM(jornadas) AS jornadas,
               COALESCE(SUM(horas_trabajadas), 0) AS horas_trabajadas,
               CASE WHEN SUM(jornadas) > 0
                    THEN ROUND((SUM(total_labor) / SUM(jornadas))::numeric, 2)
                    ELSE NULL END AS total_unitario,
               SUM(total_labor) AS costo_total,
               ROUND(
                   SUM(total_labor)::numeric
                   / NULLIF(SUM(SUM(total_labor)) OVER (PARTITION BY tipo_pago), 0) * 100, 2
               ) AS pct_pago,
               nombre_campo
        FROM appsheet.tarjas_reporte {where}
        GROUP BY tipo_pago, "Nombre Labor", "CC", nombre_campo
        ORDER BY tipo_pago DESC, "Nombre Labor", "CC"
    """, params)
    rows = _rows_to_dicts(cur)

    fmtCLP = _fmt_clp
    fmtPct = lambda v: f"{float(v):.2f} %" if v is not None else "—"
    rows_html = "".join(
        f'<tr><td>{r["tipo_pago"]}</td><td>{r["labor"]}</td><td>{r["centro_costo"]}</td>'
        f'<td class="num">{r["jornadas"]}</td>'
        f'<td class="num">{fmtCLP(r["total_unitario"])}</td>'
        f'<td class="total">{fmtCLP(r["costo_total"])}</td>'
        f'<td class="num">{fmtPct(r["pct_pago"])}</td></tr>'
        for r in rows
    )
    header = _pdf_header("Detalle operacional — Tarjas Contratistas", fecha_inicio, fecha_termino, empresa)
    return f"""
    {header}
    <table><thead>
      <tr><th>Tipo pago</th><th>Labor</th><th>CC</th>
      <th class="num">Jornadas</th><th class="num">Unitario</th>
      <th class="num">Total</th><th class="num">% pago</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    """


def _html_contratista(cur, fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None) -> str:
    where, params = _base_where_pagos(fecha_inicio, fecha_termino, empresa, contratista)
    cur.execute(f"""
        SELECT trabajador, contratista, labor, tipo_pago,
               COALESCE(SUM(total_trabajado), 0) AS total,
               fecha::date::text AS fecha
        FROM appsheet.tarjas_pagos {where}
        GROUP BY trabajador, contratista, labor, tipo_pago, fecha::date
        ORDER BY contratista, trabajador, fecha::date
    """, params)
    rows = _rows_to_dicts(cur)

    fmtCLP = _fmt_clp
    rows_html = "".join(
        f'<tr><td>{r["trabajador"]}</td><td>{r["contratista"]}</td><td>{r["labor"]}</td>'
        f'<td>{r["tipo_pago"]}</td><td>{_fmt_date_display(r["fecha"])}</td><td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in rows
    )
    header = _pdf_header("Por persona operacional — Tarjas Contratistas", fecha_inicio, fecha_termino, empresa)
    return f"""
    {header}
    <table><thead>
      <tr><th>Trabajador</th><th>Contratista</th><th>Labor</th>
      <th>Tipo de pago</th><th>Fecha</th><th class="num">Total</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    """


def _html_resumen_persona(cur, fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None) -> str:
    where, params = _base_where_pagos(fecha_inicio, fecha_termino, empresa, contratista)
    cur.execute(f"""
        SELECT trabajador, tipo_pago, fecha::date::text AS fecha,
               COALESCE(SUM(total_trabajado), 0) AS total
        FROM appsheet.tarjas_pagos {where}
        GROUP BY trabajador, tipo_pago, fecha::date
        ORDER BY trabajador, tipo_pago, fecha::date
    """, params)
    rows = _rows_to_dicts(cur)

    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        k = (r["trabajador"] or "", r["tipo_pago"] or "")
        if k not in workers:
            workers[k] = {"by_date": {}, "total": 0}
        workers[k]["by_date"][r["fecha"]] = workers[k]["by_date"].get(r["fecha"], 0) + float(r["total"] or 0)
        workers[k]["total"] += float(r["total"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    n_dates = len(dates)
    date_pct = f"{int(63 / max(n_dates, 1))}%" if n_dates else "5%"
    date_headers = "".join(
        f'<th class="num" style="width:{date_pct}">{datetime.date.fromisoformat(d).day}</th>'
        for d in dates
    )
    rows_html = ""
    prev = None
    fmtCLP = _fmt_clp
    for (trab, tipo), entry in sorted_workers:
        is_first = prev != trab
        prev = trab
        cls = "worker-first" if is_first else ""
        rows_html += f'<tr class="{cls}"><td class="col-worker">{"<b>" + trab + "</b>" if is_first else ""}</td><td class="col-tipo">{tipo}</td>'
        for d in dates:
            v = entry["by_date"].get(d, 0)
            rows_html += f'<td class="num" style="width:{date_pct}">{"" if not v else fmtCLP(v)}</td>'
        rows_html += f'<td class="col-total">{fmtCLP(entry["total"])}</td></tr>'

    header = _pdf_header("Resumen por persona — Tarjas Contratistas", fecha_inicio, fecha_termino, empresa)
    return f"""
    {header}
    <table class="pivot-table"><thead>
      <tr><th class="col-worker">Trabajador</th><th class="col-tipo">Tipo pago</th>{date_headers}<th class="col-total">Total</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    """


def _html_resumen_horas(cur, fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None) -> str:
    where, params = _base_where_pagos(fecha_inicio, fecha_termino, empresa, contratista)
    cur.execute(f"""
        SELECT trabajador, tipo_pago, fecha::date::text AS fecha,
               COALESCE(SUM(CASE WHEN horas_extras ~ '^[0-9]+(\.[0-9]+)?$'
               THEN horas_extras::numeric ELSE 0 END), 0)::numeric AS horas
        FROM appsheet.tarjas_pagos {where}
        GROUP BY trabajador, tipo_pago, fecha::date
        ORDER BY trabajador, tipo_pago, fecha::date
    """, params)
    rows = _rows_to_dicts(cur)

    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        k = (r["trabajador"] or "", r["tipo_pago"] or "")
        if k not in workers:
            workers[k] = {"by_date": {}, "total": 0}
        workers[k]["by_date"][r["fecha"]] = workers[k]["by_date"].get(r["fecha"], 0) + (r["horas"] or 0)
        workers[k]["total"] += (r["horas"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    n_dates = len(dates)
    date_pct = f"{int(63 / max(n_dates, 1))}%" if n_dates else "5%"
    date_headers = "".join(
        f'<th class="num" style="width:{date_pct}">{datetime.date.fromisoformat(d).day}</th>'
        for d in dates
    )
    rows_html = ""
    prev = None
    for (trab, tipo), entry in sorted_workers:
        is_first = prev != trab
        prev = trab
        cls = "worker-first" if is_first else ""
        rows_html += f'<tr class="{cls}"><td class="col-worker">{"<b>" + trab + "</b>" if is_first else ""}</td><td class="col-tipo">{tipo}</td>'
        for d in dates:
            v = entry["by_date"].get(d, 0)
            rows_html += f'<td class="num" style="width:{date_pct}">{v if v else ""}</td>'
        rows_html += f'<td class="col-total">{entry["total"]} h</td></tr>'

    header = _pdf_header("Horas extra por persona — Tarjas Contratistas", fecha_inicio, fecha_termino, empresa)
    return f"""
    {header}
    <table class="pivot-table"><thead>
      <tr><th class="col-worker">Trabajador</th><th class="col-tipo">Tipo pago</th>{date_headers}<th class="col-total">Total hrs</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    """


def _html_detalle_tractorista(cur, fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None) -> str:
    filters = ["fecha BETWEEN %s AND %s", _TRACTORISTA_SQL]
    params: list = [fecha_inicio, fecha_termino]
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(empresa)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    where = "WHERE " + " AND ".join(filters)

    cur.execute(f"""
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
    """, params)
    rows = _rows_to_dicts(cur)

    fmtCLP = _fmt_clp
    rows_html = "".join(
        f'<tr><td>{r["tipo_pago"]}</td><td>{r["centro_costo"]}</td><td>{r["labor"]}</td>'
        f'<td class="num">{r["jornadas"]}</td>'
        f'<td class="num">{fmtCLP(r["total_unitario"])}</td>'
        f'<td class="total">{fmtCLP(r["costo_total"])}</td>'
        f'<td>{r["contratista"]}</td></tr>'
        for r in rows
    )
    header = _pdf_header("Detalle tractorista — Tarjas", fecha_inicio, fecha_termino, empresa)
    return f"""
    {header}
    <table><thead>
      <tr><th>Tipo pago</th><th>CC</th><th>Labor</th>
      <th class="num">Jornadas</th><th class="num">Unitario</th>
      <th class="num">Total</th><th>Contratista</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    """


def _html_general_tractorista(cur, fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None) -> str:
    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(empresa)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    where = "WHERE " + " AND ".join(filters)

    cur.execute(f"""
        SELECT labor,
               ROUND(AVG(total_tractor)::numeric, 2) AS avg_rate,
               COALESCE(SUM(total_tractor), 0) AS total
        FROM appsheet.tarjas_pagos {where}
        GROUP BY labor ORDER BY total DESC
    """, params)
    labor_rows = _rows_to_dicts(cur)

    cur.execute(f"""
        SELECT trabajador, contratista,
               ROUND(AVG(total_tractor)::numeric, 2) AS avg_rate,
               COALESCE(SUM(total_tractor), 0) AS total
        FROM appsheet.tarjas_pagos {where}
        GROUP BY trabajador, contratista ORDER BY total DESC
    """, params)
    ranking_rows = _rows_to_dicts(cur)

    fmtCLP = _fmt_clp
    labor_html = "".join(
        f'<tr><td>{r["labor"]}</td>'
        f'<td class="num">{fmtCLP(r["avg_rate"])}</td>'
        f'<td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in labor_rows
    )
    ranking_html = "".join(
        f'<tr><td>{r["trabajador"]}</td><td>{r["contratista"]}</td>'
        f'<td class="num">{fmtCLP(r["avg_rate"])}</td>'
        f'<td class="total">{fmtCLP(r["total"])}</td></tr>'
        for r in ranking_rows
    )
    header = _pdf_header("General tractorista — Tarjas", fecha_inicio, fecha_termino, empresa)
    return f"""
    {header}
    <p class="section-title">Ganancia promedio por labor</p>
    <table><thead>
      <tr><th>Labor</th><th class="num">Promedio</th><th class="num">Total</th></tr>
    </thead><tbody>{labor_html}</tbody></table>
    <p class="section-title">Ranking por persona</p>
    <table><thead>
      <tr><th>Trabajador</th><th>Contratista</th><th class="num">Promedio</th><th class="num">Total</th></tr>
    </thead><tbody>{ranking_html}</tbody></table>
    """


def _html_resumen_tractorista(cur, fecha_inicio: str, fecha_termino: str, empresa: str | None, contratista: str | None = None) -> str:
    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(empresa)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    where = "WHERE " + " AND ".join(filters)

    cur.execute(f"""
        SELECT trabajador, tipo_pago, fecha::date::text AS fecha,
               COALESCE(SUM(total_tractor), 0) AS total_tractor
        FROM appsheet.tarjas_pagos {where}
        GROUP BY trabajador, tipo_pago, fecha::date
        ORDER BY trabajador, tipo_pago, fecha::date
    """, params)
    rows = _rows_to_dicts(cur)

    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        k = (r["trabajador"] or "", r["tipo_pago"] or "")
        if k not in workers:
            workers[k] = {"by_date": {}, "total": 0}
        workers[k]["by_date"][r["fecha"]] = workers[k]["by_date"].get(r["fecha"], 0) + float(r["total_tractor"] or 0)
        workers[k]["total"] += float(r["total_tractor"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    n_dates = len(dates)
    date_pct = f"{int(63 / max(n_dates, 1))}%" if n_dates else "5%"
    date_headers = "".join(
        f'<th class="num" style="width:{date_pct}">{datetime.date.fromisoformat(d).day}</th>'
        for d in dates
    )
    rows_html = ""
    prev = None
    fmtCLP = _fmt_clp
    for (trab, tipo), entry in sorted_workers:
        is_first = prev != trab
        prev = trab
        cls = "worker-first" if is_first else ""
        rows_html += f'<tr class="{cls}"><td class="col-worker">{"<b>" + trab + "</b>" if is_first else ""}</td><td class="col-tipo">{tipo}</td>'
        for d in dates:
            v = entry["by_date"].get(d, 0)
            rows_html += f'<td class="num" style="width:{date_pct}">{"" if not v else fmtCLP(v)}</td>'
        rows_html += f'<td class="col-total">{fmtCLP(entry["total"])}</td></tr>'

    header = _pdf_header("Resumen tractorista — Tarjas", fecha_inicio, fecha_termino, empresa)
    return f"""
    {header}
    <table class="pivot-table"><thead>
      <tr><th class="col-worker">Trabajador</th><th class="col-tipo">Tipo pago</th>{date_headers}<th class="col-total">Total</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    """


_REPORT_GENERATORS = {
    "general":              _html_general,
    "detalle":              _html_detalle,
    "contratista":          _html_contratista,
    "resumen-persona":      _html_resumen_persona,
    "resumen-horas":        _html_resumen_horas,
    "detalle-tractorista":  _html_detalle_tractorista,
    "general-tractorista":  _html_general_tractorista,
    "resumen-tractorista":  _html_resumen_tractorista,
}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/reportes", response_class=HTMLResponse)
async def reportes_page(request: Request):
    return _templates.TemplateResponse(request, "reportes.html", {
        "reports": AVAILABLE_REPORTS,
    })


@router.get("/api/reportes/bulk-pdf")
async def bulk_pdf_download(
    reports: str = Query(..., description="Comma-separated report IDs"),
    fecha_inicio: str = Query(...),
    fecha_termino: str = Query(...),
    empresa: str = Query(None),
    contratista: str = Query(None),
):
    if not _DATE_RE.match(fecha_inicio) or not _DATE_RE.match(fecha_termino):
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    selected = [r.strip() for r in reports.split(",") if r.strip()]
    unknown = [r for r in selected if r not in _REPORT_GENERATORS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown reports: {unknown}")
    if not selected:
        raise HTTPException(status_code=400, detail="No reports selected")

    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")

    sections: list[str] = []
    try:
        with conn.cursor() as cur:
            for report_id in selected:
                generator = _REPORT_GENERATORS[report_id]
                section_html = generator(cur, fecha_inicio, fecha_termino, empresa, contratista)
                sections.append(section_html)
    finally:
        conn.close()

    page_break = '<div class="page-break"></div>'
    body = page_break.join(sections)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{_PDF_CSS}</style>
</head><body>
{body}
</body></html>"""

    buf = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html), dest=buf)
    buf.seek(0)

    filename = f"reportes_{fecha_inicio}_{fecha_termino}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
