"""
controllers/looker_controller.py
---------------------------------
CRUD for Looker Studio report links.

Routes:
  GET  /looker                         → Looker Studio reports page (UI)
  GET  /api/looker/reports             → List all reports
  POST /api/looker/reports             → Create a new report
  PUT  /api/looker/reports/{id}        → Update an existing report
  DELETE /api/looker/reports/{id}      → Delete a report

Table: public.looker_reports
  id          SERIAL PRIMARY KEY
  name        TEXT NOT NULL
  description TEXT
  url         TEXT NOT NULL
  category    TEXT
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from auth import require_auth
from db import get_connection

logger = logging.getLogger("controllers.looker")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates
    _ensure_table()


def _ensure_table() -> None:
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.looker_reports (
                    id          SERIAL PRIMARY KEY,
                    name        TEXT NOT NULL,
                    description TEXT,
                    url         TEXT NOT NULL,
                    category    TEXT,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Could not ensure looker_reports table: %s", exc)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ReportIn(BaseModel):
    name: str
    description: str = ""
    url: str
    category: str = ""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@router.get("/looker", response_class=HTMLResponse)
async def looker_page(request: Request):
    return _templates.TemplateResponse(request, "looker.html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@router.get("/api/looker/reports")
async def list_reports():
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, url, category,
                       TO_CHAR(created_at AT TIME ZONE 'America/Santiago', 'DD/MM/YYYY HH24:MI') AS created_at,
                       TO_CHAR(updated_at AT TIME ZONE 'America/Santiago', 'DD/MM/YYYY HH24:MI') AS updated_at
                FROM public.looker_reports
                ORDER BY category, name
            """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
    return {"reports": rows}


@router.post("/api/looker/reports", status_code=201)
async def create_report(body: ReportIn):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="El nombre es obligatorio")
    if not body.url.strip():
        raise HTTPException(status_code=422, detail="La URL es obligatoria")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.looker_reports (name, description, url, category)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (body.name.strip(), body.description.strip(), body.url.strip(), body.category.strip()))
            new_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return {"id": new_id}


@router.put("/api/looker/reports/{report_id}")
async def update_report(report_id: int, body: ReportIn):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="El nombre es obligatorio")
    if not body.url.strip():
        raise HTTPException(status_code=422, detail="La URL es obligatoria")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE public.looker_reports
                SET name = %s, description = %s, url = %s, category = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (body.name.strip(), body.description.strip(), body.url.strip(), body.category.strip(), report_id))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Reporte no encontrado")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/api/looker/reports/{report_id}")
async def delete_report(report_id: int):
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.looker_reports WHERE id = %s RETURNING id", (report_id,))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Reporte no encontrado")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
