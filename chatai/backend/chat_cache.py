"""
chat_cache.py
-------------
Semantic cache for chat responses using pgvector + Gemini embeddings.

Flow:
  1. get(question)  → returns (reply, traces) if similar question cached and not expired
  2. put(question, reply, traces)  → stores embedding + response
  3. cleanup()  → deletes expired entries (called lazily)

Similarity threshold: cosine distance < 0.08  (≈ cosine similarity > 0.92)
TTL: 1h for time-sensitive questions ("hoy", "ayer", "este mes"), 6h otherwise.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

import pg_client as pg

_log = logging.getLogger("chat_cache")

SIMILARITY_THRESHOLD = 0.08   # cosine distance — lower = more similar
TTL_SHORT_HOURS      = 1      # for time-sensitive questions
TTL_LONG_HOURS       = 6      # for historical / stable questions

_TIME_SENSITIVE = re.compile(
    r"\b(hoy|ayer|este mes|esta semana|esta temporada|ahora|hoy día|"
    r"últimos \d+|último mes|último año|this month|today|yesterday)\b",
    re.IGNORECASE,
)


def _ttl(question: str) -> int:
    return TTL_SHORT_HOURS if _TIME_SENSITIVE.search(question) else TTL_LONG_HOURS


def _get_conn():
    conn = pg._get_conn()
    register_vector(conn)
    return conn


def _ensure_charts_column() -> None:
    """Add charts JSONB column to chat_cache if it doesn't exist yet."""
    try:
        conn = pg._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE public.chat_cache ADD COLUMN IF NOT EXISTS charts JSONB")
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        _log.warning("Could not add charts column to chat_cache: %s", e)


def get(question: str, embedding: list[float]) -> Optional[tuple[str, list, list]]:
    """Return (reply, traces, charts) from cache or None on miss."""
    try:
        conn = _get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, reply, traces, charts,
                           embedding <=> %s::vector AS distance
                    FROM public.chat_cache
                    WHERE expires_at > NOW()
                      AND embedding <=> %s::vector < %s
                    ORDER BY distance
                    LIMIT 1
                """, (embedding, embedding, SIMILARITY_THRESHOLD))
                row = cur.fetchone()
                if not row:
                    return None
                cur.execute("""
                    UPDATE public.chat_cache
                    SET hit_count  = hit_count + 1,
                        last_hit_at = NOW()
                    WHERE id = %s
                """, (row["id"],))
                conn.commit()
                _log.info("cache hit id=%s dist=%.4f", row["id"], row["distance"])
                traces = row["traces"] if row["traces"] else []
                charts = row["charts"] if row["charts"] else []
                return row["reply"], traces, charts
        finally:
            conn.close()
    except Exception as e:
        _log.warning("cache get error: %s", e)
        return None


def put(question: str, embedding: list[float], reply: str, traces: list, charts: list = None) -> None:
    """Store a question+response in cache."""
    ttl = _ttl(question)
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.chat_cache
                      (question_raw, embedding, reply, traces, charts, ttl_hours, expires_at)
                    VALUES (%s, %s::vector, %s, %s, %s, %s, NOW() + (%s || ' hours')::INTERVAL)
                """, (
                    question,
                    embedding,
                    reply,
                    json.dumps(traces, ensure_ascii=False, default=str),
                    json.dumps(charts, ensure_ascii=False, default=str) if charts else None,
                    ttl,
                    ttl,
                ))
            conn.commit()
            _log.info("cache put ttl=%dh question=%.60s", ttl, question)
        finally:
            conn.close()
    except Exception as e:
        _log.warning("cache put error: %s", e)


def cleanup() -> int:
    """Delete expired cache entries. Returns count deleted."""
    try:
        conn = pg._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public.chat_cache WHERE expires_at <= NOW()")
                deleted = cur.rowcount
            conn.commit()
            if deleted:
                _log.info("cache cleanup deleted=%d", deleted)
            return deleted
        finally:
            conn.close()
    except Exception as e:
        _log.warning("cache cleanup error: %s", e)
        return 0
