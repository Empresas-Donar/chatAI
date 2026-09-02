"""
controllers/reports_controller.py
----------------------------------
Bulk PDF download page — lets users select multiple reports and download
them as a single merged PDF.

Every report section is built by the SAME function the corresponding
standalone PDF endpoint uses (imported from tarjas_controller.py), so the
bulk section and the individual download are byte-for-byte identical given
the same filters (issue #116).

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
_EXTRA_BULK_CSS = """
.page-break { page-break-before: always; }
.report-divider { border: none; border-top: 2px solid #333333; margin: 16px 0 12px 0; }
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
    "resumen-tractorista": lambda cur, fi, ft, empresa, contratista=None: tc._build_resumen_persona_tractorista_html(
        cur, fi, ft, contratista=contratista, empresa=empresa
    ),
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
