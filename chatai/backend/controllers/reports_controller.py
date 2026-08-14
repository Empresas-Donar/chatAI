"""
controllers/reports_controller.py
----------------------------------
Bulk PDF download page — lets users select multiple reports and download
them as a single merged PDF.

Every report section is built by the SAME function the corresponding
standalone PDF endpoint uses (imported from tarjas_controller.py), so the
bulk section and the individual download are byte-for-byte identical given
the same filters (issue #116). The one exception is "resumen-tractorista",
which has no standalone PDF endpoint to share — only a screen + Excel
version exist for it — so it keeps its own local implementation here.

Routes:
  GET  /reportes                     → Report selection page
  GET  /api/reportes/bulk-pdf        → Generates and returns merged PDF
"""

import io
import re

from auth import require_auth
from db import get_connection
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from xhtml2pdf import pisa

import controllers.tarjas_controller as tc

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# resumen-tractorista has no standalone PDF to share; needs its own WHERE.
_TRACTORISTA_PAGOS_SQL = "(LOWER(TRIM(tipo_pago)) = 'tractorista')"

AVAILABLE_REPORTS = [
    # ── Contratistas — same order as the navigation menu ──────────────────────
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
        "id": "general",
        "label": "General operacional",
        "description": "Ganancia promedio por labor y ranking por persona",
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
        "id": "jornadas-trabajador",
        "label": "Jornadas por trabajador",
        "description": "Conteo de jornadas (días distintos) por trabajador",
        "category": "Tarjas — Contratistas",
    },
    {
        "id": "bono-mensual",
        "label": "Bonos mensuales",
        "description": "Bonos mensuales pagados por trabajador",
        "category": "Tarjas — Contratistas",
    },
    {
        "id": "hora-ponderada-9h",
        "label": "Hora ponderada 9h",
        "description": "Costo por hora proyectado a jornada de 9 horas, por labor y CC",
        "category": "Tarjas — Contratistas",
    },
    # ── Tractoristas — same order as the navigation menu ─────────────────────
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


# ── CSS additions on top of tarjas_controller._PDF_CSS ────────────────────────
# page-break/report-divider: needed to join multiple sections into one PDF.
# pivot-table/.col-*: only used by _html_resumen_tractorista below (the one
# report with no standalone PDF to inherit styling from).
_EXTRA_BULK_CSS = """
.page-break { page-break-before: always; }
.report-divider { border: none; border-top: 2px solid #333333; margin: 16px 0 12px 0; }
.pivot-table { table-layout: fixed; width: 100%; }
.pivot-table th { font-size: 6.5pt; padding: 4px 3px; }
.pivot-table td { font-size: 6.5pt; padding: 3px 3px; }
.pivot-table .col-worker { width: 18%; }
.pivot-table .col-tipo   { width: 9%; }
.pivot-table .col-total  { width: 10%; text-align: right; font-weight: bold; border-left: 1.5px solid #888888; }
"""


# ── The one report without a standalone PDF endpoint ──────────────────────────


def _html_resumen_tractorista(
    cur,
    fecha_inicio: str,
    fecha_termino: str,
    empresa: str | None,
    contratista: str | None = None,
) -> str:
    """No standalone PDF exists for this report (only screen + Excel), so
    there is nothing to share code with — implemented directly here."""
    filters = ["fecha::date BETWEEN %s AND %s", _TRACTORISTA_PAGOS_SQL]
    params: list = [fecha_inicio, fecha_termino]
    if empresa:
        filters.append("nombre_campo = %s")
        params.append(empresa)
    if contratista:
        filters.append("contratista = %s")
        params.append(contratista)
    where = "WHERE " + " AND ".join(filters)

    cur.execute(
        f"""
        SELECT trabajador, tipo_pago, fecha::date::text AS fecha,
               COALESCE(SUM(total_tractor), 0) AS total_tractor
        FROM appsheet.tarjas_pagos {where}
        GROUP BY trabajador, tipo_pago, fecha::date
        ORDER BY trabajador, tipo_pago, fecha::date
    """,
        params,
    )
    rows = tc._rows_to_dicts(cur)

    dates = sorted({r["fecha"] for r in rows})
    workers: dict = {}
    for r in rows:
        k = (r["trabajador"] or "", r["tipo_pago"] or "")
        if k not in workers:
            workers[k] = {"by_date": {}, "total": 0}
        workers[k]["by_date"][r["fecha"]] = workers[k]["by_date"].get(
            r["fecha"], 0
        ) + float(r["total_tractor"] or 0)
        workers[k]["total"] += float(r["total_tractor"] or 0)
    sorted_workers = sorted(workers.items(), key=lambda x: -x[1]["total"])

    n_dates = len(dates)
    date_pct = f"{int(63 / max(n_dates, 1))}%" if n_dates else "5%"
    date_headers = "".join(
        f'<th class="num" style="width:{date_pct}">{tc.datetime.date.fromisoformat(d).day}</th>'
        for d in dates
    )
    rows_html = ""
    prev = None
    fmtCLP = tc._fmt_clp
    for (trab, tipo), entry in sorted_workers:
        is_first = prev != trab
        prev = trab
        cls = "worker-first" if is_first else ""
        rows_html += f'<tr class="{cls}"><td class="col-worker">{"<b>" + trab + "</b>" if is_first else ""}</td><td class="col-tipo">{tipo}</td>'
        for d in dates:
            v = entry["by_date"].get(d, 0)
            rows_html += f'<td class="num" style="width:{date_pct}">{"" if not v else fmtCLP(v)}</td>'
        rows_html += f'<td class="col-total">{fmtCLP(entry["total"])}</td></tr>'

    header = tc._pdf_header(
        tc._pdf_title("Resumen Tractorista", contratista),
        fecha_inicio,
        fecha_termino,
        {"Empresa": empresa, "Contratista": contratista},
    )
    return f"""
    {header}
    <table class="pivot-table"><thead>
      <tr><th class="col-worker">Trabajador</th><th class="col-tipo">Tipo pago</th>{date_headers}<th class="col-total">Total</th></tr>
    </thead><tbody>{rows_html}</tbody></table>
    """


# ── Report registry ─────────────────────────────────────────────────────────
# Each generator is called as generator(cur, fecha_inicio, fecha_termino,
# empresa, contratista) — the bulk page's fixed filter set. Reports that take
# extra filters on their own standalone page (CC, Labor, Campo, Mes) simply
# don't receive them here, matching how those extra filters were already
# absent from the bulk page's UI before this refactor.

_REPORT_GENERATORS = {
    "detalle": lambda cur, fi, ft, empresa, contratista=None: tc._build_detalle_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "contratista": lambda cur, fi, ft, empresa, contratista=None: tc._build_contratista_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "general": lambda cur, fi, ft, empresa, contratista=None: tc._build_general_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "resumen-persona": lambda cur, fi, ft, empresa, contratista=None: tc._build_resumen_persona_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "resumen-horas": lambda cur, fi, ft, empresa, contratista=None: tc._build_resumen_horas_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "jornadas-trabajador": lambda cur, fi, ft, empresa, contratista=None: tc._build_jornadas_trabajador_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "bono-mensual": lambda cur, fi, ft, empresa, contratista=None: tc._build_bono_mensual_html(
        cur, fi, ft, empresa=empresa, contratista=contratista
    ),
    "hora-ponderada-9h": lambda cur, fi, ft, empresa, contratista=None: tc._build_hora_ponderada_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "detalle-tractorista": lambda cur, fi, ft, empresa, contratista=None: tc._build_detalle_tractorista_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "general-tractorista": lambda cur, fi, ft, empresa, contratista=None: tc._build_general_tractorista_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
    "resumen-tractorista": _html_resumen_tractorista,
}


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/reportes", response_class=HTMLResponse)
async def reportes_page(request: Request):
    return _templates.TemplateResponse(
        request,
        "reportes.html",
        {
            "reports": AVAILABLE_REPORTS,
        },
    )


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
        raise HTTPException(
            status_code=503, detail="Error de conexión a la base de datos"
        )

    sections: list[str] = []
    try:
        with conn.cursor() as cur:
            for report_id in selected:
                generator = _REPORT_GENERATORS[report_id]
                section_html = generator(
                    cur, fecha_inicio, fecha_termino, empresa, contratista
                )
                sections.append(section_html)
    finally:
        conn.close()

    page_break = '<div class="page-break"></div>'
    body = page_break.join(sections)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{tc._PDF_CSS}{_EXTRA_BULK_CSS}</style>
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
