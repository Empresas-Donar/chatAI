"""
controllers/contratistas_controller.py
--------------------------------------
CRUD for the intranet contractor master.

Routes:
  GET    /utilidades/contratistas       → page
  GET    /api/contratistas              → list
  POST   /api/contratistas              → create
  PATCH  /api/contratistas/{id}         → update
  DELETE /api/contratistas/{id}         → delete when nothing links to it

The table lives in schema intranet. App catalogs keep a nullable
id_intranet_contratistas text column, with no foreign key. Deleting a
master row clears that text and leaves the AppSheet row in place.
"""

import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg2 import errors
from pydantic import BaseModel

from auth import require_admin, require_auth
from db import get_connection

logger = logging.getLogger("controllers.contratistas")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None
_SQL_DIR = Path(__file__).resolve().parents[3] / "sql" / "intranet"

_SELECT_SQL = """
SELECT
  c.id_intranet,
  c.nombre,
  c.nombre_corto,
  c.rut,
  c.activo,
  (
    SELECT COUNT(*)
    FROM appsheet.tarjas_contratistas t
    WHERE t.id_intranet_contratistas = c.id_intranet
  )::int AS enlaces_tarjas,
  (
    SELECT COUNT(*)
    FROM appsheet.cosecha_zuniga_contratistas z
    WHERE z.id_intranet_contratistas = c.id_intranet
  )::int AS enlaces_cosecha,
  (
    EXISTS (
      SELECT 1
      FROM appsheet.tarjas_contratistas t
      JOIN appsheet.tarjas_pagos p
        ON lower(unaccent(btrim(p.contratista))) = lower(unaccent(btrim(t.nombre)))
      WHERE t.id_intranet_contratistas = c.id_intranet
        AND p.fecha::date >= (CURRENT_DATE - INTERVAL '1 month')::date
    )
    OR EXISTS (
      SELECT 1
      FROM appsheet.cosecha_zuniga_contratistas z
      JOIN appsheet.cosecha_zuniga_escaneo e
        ON e.id_contratista = z.id_contratista
      WHERE z.id_intranet_contratistas = c.id_intranet
        AND COALESCE(e.fecha, e.fecha_y_hora::date)
            >= (CURRENT_DATE - INTERVAL '1 month')::date
    )
  ) AS con_actividad
FROM intranet.contratistas c
"""

_LIST_SQL = _SELECT_SQL + "ORDER BY lower(btrim(c.nombre)), c.id_intranet"


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates
    _ensure_schema()


def _ensure_schema() -> None:
    try:
        files = sorted(_SQL_DIR.glob("*.sql"))
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                for path in files:
                    cur.execute(path.read_text(encoding="utf-8"))
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Could not ensure intranet.contratistas: %s", exc)


class ContratistaIn(BaseModel):
    nombre: str
    nombre_corto: str | None = None
    rut: str | None = None
    activo: bool = True


def _connect():
    try:
        return get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")


def _clean(value: str | None, limit: int) -> str | None:
    text = " ".join((value or "").split())
    if not text:
        return None
    if len(text) > limit:
        raise HTTPException(status_code=422, detail=f"El texto supera {limit} caracteres")
    return text


def _fields(body: ContratistaIn) -> tuple[str, str | None, str | None, bool]:
    nombre = _clean(body.nombre, 200)
    if not nombre:
        raise HTTPException(status_code=422, detail="El nombre es obligatorio")
    corto = _clean(body.nombre_corto, 80)
    rut = _clean(body.rut, 20)
    if rut:
        rut = rut.upper()
    return nombre, corto, rut, body.activo


def _rows(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    rows = []
    for rec in cur.fetchall():
        row = dict(zip(cols, rec))
        row["enlaces_tarjas"] = int(row["enlaces_tarjas"] or 0)
        row["enlaces_cosecha"] = int(row["enlaces_cosecha"] or 0)
        row["activo"] = bool(row["activo"])
        row["con_actividad"] = bool(row["con_actividad"])
        rows.append(row)
    return rows


def _one(cur) -> dict:
    rows = _rows(cur)
    if not rows:
        raise HTTPException(status_code=404, detail="Contratista no encontrado")
    return rows[0]


def _new_id(cur) -> str:
    for _ in range(5):
        candidate = secrets.token_hex(8)
        cur.execute(
            "SELECT 1 FROM intranet.contratistas WHERE id_intranet = %s",
            (candidate,),
        )
        if cur.fetchone() is None:
            return candidate
    raise HTTPException(status_code=503, detail="No se pudo asignar un id")


@router.get("/utilidades/contratistas", response_class=HTMLResponse)
async def contratistas_page(request: Request, _admin=Depends(require_admin)):
    return _templates.TemplateResponse(request, "contratistas.html")


def _fetch_one(cur, contratista_id: str) -> dict:
    cur.execute(_SELECT_SQL + "WHERE c.id_intranet = %s", (contratista_id,))
    return _one(cur)


@router.get("/api/contratistas")
async def list_contratistas(_admin=Depends(require_admin)):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_LIST_SQL)
            rows = _rows(cur)
            cur.execute(
                "SELECT to_char((CURRENT_DATE - INTERVAL '1 month')::date, 'DD/MM/YYYY')"
            )
            desde = cur.fetchone()[0]
    finally:
        conn.close()
    return {"contratistas": rows, "actividad_desde": desde}


@router.post("/api/contratistas", status_code=201)
async def create_contratista(body: ContratistaIn, _admin=Depends(require_admin)):
    nombre, corto, rut, activo = _fields(body)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            new_id = _new_id(cur)
            try:
                cur.execute(
                    """
                    INSERT INTO intranet.contratistas
                      (id_intranet, nombre, nombre_corto, rut, activo)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (new_id, nombre, corto, rut, activo),
                )
            except errors.UniqueViolation:
                conn.rollback()
                raise HTTPException(
                    status_code=409, detail="Ya existe un contratista con ese nombre"
                )
            row = _fetch_one(cur, new_id)
        conn.commit()
    finally:
        conn.close()
    return row


@router.patch("/api/contratistas/{contratista_id}")
async def update_contratista(
    contratista_id: str, body: ContratistaIn, _admin=Depends(require_admin)
):
    nombre, corto, rut, activo = _fields(body)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    UPDATE intranet.contratistas
                    SET nombre = %s,
                        nombre_corto = %s,
                        rut = %s,
                        activo = %s,
                        updated_at = NOW()
                    WHERE id_intranet = %s
                    """,
                    (nombre, corto, rut, activo, contratista_id),
                )
            except errors.UniqueViolation:
                conn.rollback()
                raise HTTPException(
                    status_code=409, detail="Ya existe un contratista con ese nombre"
                )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Contratista no encontrado")
            row = _fetch_one(cur, contratista_id)
        conn.commit()
    finally:
        conn.close()
    return row


@router.delete("/api/contratistas/{contratista_id}")
async def delete_contratista(contratista_id: str, _admin=Depends(require_admin)):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM intranet.contratistas WHERE id_intranet = %s",
                (contratista_id,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Contratista no encontrado")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
