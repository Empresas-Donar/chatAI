"""
db.py
-----
PostgreSQL helper. A small thread-safe pool avoids a new Cloud SQL TCP
handshake on every request (PATCH after GET was failing with connect timeout).
Existing callers still use get_connection() / conn.close().
"""

import logging
import os
import threading
import time

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger("db")

_pool = None
_pool_lock = threading.Lock()
_POOL_MIN = 1
_POOL_MAX = 6


def _connect_kwargs():
    host = os.environ["DB_HOST"]
    timeout = int(os.environ.get("DB_CONNECT_TIMEOUT", "15"))
    common = {
        "dbname": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "connect_timeout": timeout,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }
    if host.startswith("/"):
        return {"host": host, **common}
    return {
        "host": host,
        "port": int(os.environ.get("DB_PORT", 5432)),
        **common,
    }


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        kwargs = _connect_kwargs()
        _pool = ThreadedConnectionPool(_POOL_MIN, _POOL_MAX, **kwargs)
        return _pool


class _PooledConnection:
    """Looks like a psycopg2 connection; close() returns it to the pool."""

    def __init__(self, raw, pool):
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_pool", pool)
        object.__setattr__(self, "_closed", False)

    def close(self):
        if object.__getattribute__(self, "_closed"):
            return
        object.__setattr__(self, "_closed", True)
        raw = object.__getattribute__(self, "_raw")
        pool = object.__getattribute__(self, "_pool")
        try:
            if not raw.closed:
                raw.rollback()
        except Exception:
            pass
        try:
            pool.putconn(raw)
        except Exception:
            try:
                raw.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        raw = object.__getattribute__(self, "_raw")
        if exc_type is None:
            raw.commit()
        else:
            raw.rollback()
        return False

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_raw"), name)


def _connect_direct():
    last = None
    for attempt in range(3):
        try:
            return psycopg2.connect(**_connect_kwargs())
        except Exception as exc:
            last = exc
            logger.warning("DB connect failed (try %s/3): %s", attempt + 1, exc)
            time.sleep(0.4 * (attempt + 1))
    raise last


def _checkout():
    pool = _get_pool()
    raw = pool.getconn()
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT 1")
        raw.rollback()
        return raw
    except Exception:
        try:
            pool.putconn(raw, close=True)
        except Exception:
            pass
        raise


def get_connection():
    last = None
    for attempt in range(3):
        try:
            pool = _get_pool()
            raw = _checkout()
            return _PooledConnection(raw, pool)
        except Exception as exc:
            last = exc
            logger.warning("DB pool getconn failed (try %s/3): %s", attempt + 1, exc)
            time.sleep(0.4 * (attempt + 1))
    logger.warning("Falling back to a direct DB connection")
    return _connect_direct()
