"""
controllers/centros_costo_controller.py
---------------------------------------
CRUD for the tarjas AppSheet cost-center catalog.

Routes:
  GET    /utilidades/centros-costo     → page
  GET    /api/centros-costo            → list
  POST   /api/centros-costo            → create
  PATCH  /api/centros-costo/{id_cc}    → update name, farm and distribution
  DELETE /api/centros-costo/{id_cc}    → delete when nothing references it

The table is appsheet.tarjas_cc. valor_odoo is the analytic distribution:
{"odoo_id": percentage}. The percentages of one row sum to 100.00.
"""

import json
import logging
import re
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg2 import errors
from pydantic import BaseModel

from auth import require_admin, require_auth
from db import get_connection

logger = logging.getLogger("controllers.centros_costo")

router = APIRouter(dependencies=[Depends(require_auth)])

_templates: Jinja2Templates = None

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")

_LIST_SQL = """
SELECT
  c.id_cc,
  c.cultivo,
  c.id_campo,
  ca.nombre AS campo,
  c.valor_odoo,
  COALESCE(u.registros, 0)::int AS registros
FROM appsheet.tarjas_cc c
LEFT JOIN appsheet.tarjas_campo ca ON ca.id_campo = c.id_campo
LEFT JOIN (
  SELECT btrim(cuartel_cc) AS id_cc, COUNT(*) AS registros
  FROM appsheet.tarjas_pagos
  WHERE btrim(COALESCE(cuartel_cc, '')) <> ''
  GROUP BY 1
) u ON u.id_cc = c.id_cc
ORDER BY c.id_campo NULLS LAST, c.id_cc
"""

_USAGE_SQL = """
SELECT
  (
    SELECT COUNT(*)
    FROM appsheet.tarjas_pagos
    WHERE btrim(COALESCE(cuartel_cc, '')) = %s
  )::int
  + (
    SELECT COUNT(*)
    FROM appsheet.tarjas_plan_diario
    WHERE btrim(COALESCE(id_cc, '')) = %s
  )::int
  + (
    SELECT COUNT(*)
    FROM appsheet.tarjas_bono_mensual
    WHERE btrim(COALESCE(id_cc, '')) = %s
  )::int
"""


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


class DistribucionIn(BaseModel):
    odoo_id: str
    porcentaje: str


class CentroCostoIn(BaseModel):
    id_cc: str | None = None
    cultivo: str
    id_campo: int
    distribucion: list[DistribucionIn] = []


def clean_code(value: str | None) -> str:
    code = (value or "").strip()
    if not _CODE_RE.match(code):
        raise HTTPException(
            status_code=422,
            detail="El código debe ser el de la app: letras, números, punto, guion o guion bajo (máximo 40).",
        )
    return code


def clean_name(value: str | None) -> str:
    name = " ".join((value or "").split())
    if not name:
        raise HTTPException(status_code=422, detail="El nombre es obligatorio")
    if len(name) > 120:
        raise HTTPException(status_code=422, detail="El nombre supera 120 caracteres")
    return name


def require_campo(id_campo: int, valid: set[int]) -> int:
    if id_campo not in valid:
        raise HTTPException(status_code=422, detail="El campo no existe")
    return id_campo


def distribution_lines(valor) -> list[dict]:
    """valor_odoo object → [{odoo_id, porcentaje}] with percentages at 2 decimals."""
    if not isinstance(valor, dict):
        return []
    lines = []
    for key, pct in valor.items():
        if key is None or str(key).strip() == "" or pct is None:
            continue
        dec = Decimal(str(pct)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        lines.append({"odoo_id": str(key), "porcentaje": format(dec, "f")})
    return lines


def clean_distribucion(lines: list[tuple[str, str]]) -> str | None:
    """Turn form lines into a valor_odoo JSON object, or None when there are none.

    Each Odoo id is numeric. Percentages use at most two decimals, are greater
    than zero, and sum to exactly 100.00. Duplicate ids are rejected.
    """
    if not lines:
        return None
    cleaned: dict[str, Decimal] = {}
    for raw_id, raw_pct in lines:
        odoo_id = str(raw_id or "").strip()
        if not re.fullmatch(r"[0-9]{1,12}", odoo_id):
            raise HTTPException(
                status_code=422,
                detail="Cada línea de la distribución necesita el id numérico de Odoo.",
            )
        if odoo_id in cleaned:
            raise HTTPException(
                status_code=422,
                detail=f"La cuenta {odoo_id} está repetida en la distribución.",
            )
        text = str(raw_pct if raw_pct is not None else "").strip().replace(",", ".")
        try:
            pct = Decimal(text)
        except Exception:
            raise HTTPException(
                status_code=422, detail="Hay un porcentaje que no es un número."
            )
        if pct != pct.quantize(Decimal("0.01")):
            raise HTTPException(
                status_code=422,
                detail="Los porcentajes usan como máximo dos decimales.",
            )
        if pct <= 0 or pct > 100:
            raise HTTPException(
                status_code=422,
                detail="Cada porcentaje tiene que ser mayor que 0 y hasta 100.",
            )
        cleaned[odoo_id] = pct.quantize(Decimal("0.01"))
    total = sum(cleaned.values(), Decimal("0.00"))
    if total != Decimal("100.00"):
        raise HTTPException(
            status_code=422,
            detail=f"La distribución tiene que sumar 100. Ahora suma {format(total, 'f')}.",
        )
    body = ", ".join(
        f"{json.dumps(key)}: {format(pct, 'f')}" for key, pct in cleaned.items()
    )
    return "{" + body + "}"


def usage_count(cur, id_cc: str) -> int:
    cur.execute(_USAGE_SQL, (id_cc, id_cc, id_cc))
    return int(cur.fetchone()[0] or 0)


def _connect():
    try:
        return get_connection()
    except Exception:
        raise HTTPException(status_code=503, detail="Error de conexión a la base de datos")


def _campos(cur) -> list[dict]:
    cur.execute(
        'SELECT id_campo, nombre FROM appsheet.tarjas_campo ORDER BY id_campo'
    )
    return [{"id_campo": row[0], "nombre": row[1]} for row in cur.fetchall()]


def _valid_campos(cur) -> set[int]:
    return {row["id_campo"] for row in _campos(cur)}


def _cuentas(cur) -> list[dict]:
    """Single-account rows, so a distribution line can show code and name."""
    cur.execute(
        """
        SELECT
          c.id_cc,
          c.cultivo,
          ca.nombre AS campo,
          (SELECT e.key FROM jsonb_each(c.valor_odoo) e LIMIT 1) AS odoo_id
        FROM appsheet.tarjas_cc c
        LEFT JOIN appsheet.tarjas_campo ca ON ca.id_campo = c.id_campo
        WHERE jsonb_typeof(c.valor_odoo) = 'object'
          AND (SELECT COUNT(*) FROM jsonb_object_keys(c.valor_odoo)) = 1
        ORDER BY c.id_campo NULLS LAST, c.id_cc
        """
    )
    return [
        {
            "id_cc": row[0],
            "cultivo": row[1],
            "campo": row[2],
            "odoo_id": row[3],
        }
        for row in cur.fetchall()
        if row[3]
    ]


def _public_row(row: dict) -> dict:
    row["distribucion"] = distribution_lines(row.pop("valor_odoo", None))
    row["con_odoo"] = bool(row["distribucion"])
    row["registros"] = int(row["registros"] or 0)
    return row


def _row_from(cur, id_cc: str) -> dict:
    cur.execute(
        f"SELECT * FROM ({_LIST_SQL}) listed WHERE id_cc = %s",
        (id_cc,),
    )
    cols = [d[0] for d in cur.description]
    rec = cur.fetchone()
    if rec is None:
        raise HTTPException(status_code=404, detail="Centro de costo no encontrado")
    return _public_row(dict(zip(cols, rec)))


def _rows(cur) -> list[dict]:
    cur.execute(_LIST_SQL)
    cols = [d[0] for d in cur.description]
    rows = []
    for rec in cur.fetchall():
        rows.append(_public_row(dict(zip(cols, rec))))
    return rows


@router.get("/utilidades/centros-costo", response_class=HTMLResponse)
async def centros_costo_page(request: Request, _admin=Depends(require_admin)):
    return _templates.TemplateResponse(request, "centros_costo.html")


@router.get("/api/centros-costo")
async def list_centros_costo(_admin=Depends(require_admin)):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            rows = _rows(cur)
            campos = _campos(cur)
            cuentas = _cuentas(cur)
    finally:
        conn.close()
    return {"centros": rows, "campos": campos, "cuentas": cuentas}


@router.post("/api/centros-costo", status_code=201)
def _distribution_payload(body: CentroCostoIn) -> str | None:
    return clean_distribucion(
        [(item.odoo_id, item.porcentaje) for item in body.distribucion]
    )


async def create_centro_costo(body: CentroCostoIn, _admin=Depends(require_admin)):
    code = clean_code(body.id_cc)
    name = clean_name(body.cultivo)
    distribucion = _distribution_payload(body)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            campo = require_campo(body.id_campo, _valid_campos(cur))
            try:
                cur.execute(
                    """
                    INSERT INTO appsheet.tarjas_cc (id_cc, cultivo, id_campo, valor_odoo)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    (code, name, campo, distribucion),
                )
            except errors.UniqueViolation:
                conn.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="Ya existe un centro de costo con ese código",
                )
            except errors.CheckViolation:
                conn.rollback()
                raise HTTPException(
                    status_code=422,
                    detail="La distribución tiene una cuenta vacía.",
                )
            row = _row_from(cur, code)
        conn.commit()
    finally:
        conn.close()
    return row


@router.patch("/api/centros-costo/{id_cc}")
async def update_centro_costo(
    id_cc: str, body: CentroCostoIn, _admin=Depends(require_admin)
):
    code = clean_code(id_cc)
    name = clean_name(body.cultivo)
    distribucion = _distribution_payload(body)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            campo = require_campo(body.id_campo, _valid_campos(cur))
            try:
                cur.execute(
                    """
                    UPDATE appsheet.tarjas_cc
                    SET cultivo = %s, id_campo = %s, valor_odoo = %s::jsonb
                    WHERE id_cc = %s
                    """,
                    (name, campo, distribucion, code),
                )
            except errors.CheckViolation:
                conn.rollback()
                raise HTTPException(
                    status_code=422,
                    detail="La distribución tiene una cuenta vacía.",
                )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Centro de costo no encontrado")
            row = _row_from(cur, code)
        conn.commit()
    finally:
        conn.close()
    return row


@router.delete("/api/centros-costo/{id_cc}")
async def delete_centro_costo(id_cc: str, _admin=Depends(require_admin)):
    code = clean_code(id_cc)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM appsheet.tarjas_cc WHERE id_cc = %s",
                (code,),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Centro de costo no encontrado")
            used = usage_count(cur, code)
            if used:
                raise HTTPException(
                    status_code=409,
                    detail=f"No se puede borrar: hay {used} registros de tarja, plan o bono con este código.",
                )
            cur.execute(
                "DELETE FROM appsheet.tarjas_cc WHERE id_cc = %s",
                (code,),
            )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
