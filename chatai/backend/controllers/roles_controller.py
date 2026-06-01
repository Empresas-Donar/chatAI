"""
controllers/roles_controller.py
--------------------------------
CRUD for user role assignments (admin / user).

Routes:
  GET    /utilidades/roles            → Roles management page (UI)
  GET    /api/roles                   → List all role entries
  POST   /api/roles                   → Assign / update a user role
  DELETE /api/roles/{email}           → Remove role entry (user loses access)

Table: public.user_roles
  email      TEXT PRIMARY KEY
  role       TEXT NOT NULL CHECK (role IN ('admin','user'))
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Access: only users with role='admin' can reach these routes.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from auth import require_auth, require_admin
from db import get_connection

logger = logging.getLogger("controllers.roles")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None

VALID_ROLES = {"admin", "user"}


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates
    _ensure_table()


def _ensure_table() -> None:
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.user_roles (
                    email      TEXT PRIMARY KEY,
                    role       TEXT NOT NULL CHECK (role IN ('admin','user')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Could not ensure user_roles table: %s", exc)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class RoleIn(BaseModel):
    email: str
    role: str


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@router.get("/utilidades/roles", response_class=HTMLResponse)
async def roles_page(request: Request, _admin=Depends(require_admin)):
    return _templates.TemplateResponse(request, "roles.html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@router.get("/api/roles")
async def list_roles(_admin=Depends(require_admin)):
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    r.email,
                    r.role,
                    TO_CHAR(r.created_at AT TIME ZONE 'America/Santiago', 'DD/MM/YYYY HH24:MI') AS created_at,
                    TO_CHAR(r.updated_at AT TIME ZONE 'America/Santiago', 'DD/MM/YYYY HH24:MI') AS updated_at,
                    TO_CHAR(MAX(h.created_at) AT TIME ZONE 'UTC' AT TIME ZONE 'America/Santiago', 'DD/MM/YYYY HH24:MI') AS last_seen,
                    COUNT(CASE WHEN h.role = 'user' THEN 1 END) AS chat_messages
                FROM public.user_roles r
                LEFT JOIN public.chat_history h ON h.username = r.email
                GROUP BY r.email, r.role, r.created_at, r.updated_at
                ORDER BY r.role, r.email
            """)
            cols = [d[0] for d in cur.description]
            rows = []
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                row["chat_messages"] = int(row["chat_messages"] or 0)
                row["last_seen"] = row["last_seen"] or None
                rows.append(row)
    finally:
        conn.close()
    return {"roles": rows}


@router.post("/api/roles", status_code=201)
async def upsert_role(body: RoleIn, _admin=Depends(require_admin)):
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(status_code=422, detail="El email es obligatorio")
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Rol inválido. Use 'admin' o 'user'")
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.user_roles (email, role)
                VALUES (%s, %s)
                ON CONFLICT (email) DO UPDATE
                  SET role = EXCLUDED.role, updated_at = NOW()
            """, (email, body.role))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/api/roles/{email:path}")
async def delete_role(email: str, _admin=Depends(require_admin)):
    email = email.strip().lower()
    try:
        conn = get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.user_roles WHERE email = %s RETURNING email",
                (email,)
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
