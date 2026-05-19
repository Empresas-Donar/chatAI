"""
core_db.py
----------
Lightweight DB connection helper for the chatai backend.
Uses psycopg2 (same driver as the root core/db.py) reading env vars already
loaded by main.py via dotenv.
"""

import os
import psycopg2


def get_connection():
    host = os.environ["DB_HOST"]
    # Cloud Run uses a Unix socket path (e.g. /cloudsql/project:region:instance)
    # psycopg2 connects via socket when host starts with '/'
    if host.startswith("/"):
        return psycopg2.connect(
            host=host,
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
    return psycopg2.connect(
        host=host,
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
