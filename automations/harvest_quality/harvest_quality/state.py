"""Append-only trace in intranet.proceso_estado. One insert per check."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

from harvest_quality.config import ROOT


def connect():
    _load_env()
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    host = os.environ["DB_HOST"]
    kwargs = dict(
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    if host.startswith("/"):
        return psycopg2.connect(host=host, **kwargs)
    return psycopg2.connect(
        host=host,
        port=int(os.environ.get("DB_PORT", 5432)),
        **kwargs,
    )


def dotenv_paths(root) -> list:
    """Local repo dotenv files. The Cloud Run image lives at /app and has none."""
    if len(root.parents) < 2:
        return []
    repo = root.parents[1]
    return [repo / ".env", repo / "chatai" / ".env"]


def _load_env() -> None:
    for path in dotenv_paths(ROOT):
        load_dotenv(path)


def last_sent_huella(conn, proceso: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT "huella"
            FROM intranet.proceso_estado
            WHERE "proceso" = %s AND "enviado"
            ORDER BY "enviado_en" DESC
            LIMIT 1
            """,
            (proceso,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def insert_check(
    conn,
    *,
    proceso: str,
    huella: str | None,
    enviado: bool,
    motivo: str,
    revisado_en: datetime,
    enviado_en: datetime | None,
) -> str:
    row_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO intranet.proceso_estado
                ("id", "proceso", "huella", "enviado", "motivo", "revisado_en", "enviado_en")
            VALUES (
                %s, %s, %s, %s, %s,
                %s AT TIME ZONE 'America/Santiago',
                %s AT TIME ZONE 'America/Santiago'
            )
            """,
            (row_id, proceso, huella, enviado, motivo, revisado_en, enviado_en),
        )
    return row_id
