"""
test_roles.py
-------------
Integration tests for the user roles system. These run against the real
production database on every deploy (Cloud Build step) to ensure no one
loses access or gains unauthorized privileges.

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_roles.py -v

Run in CI (Cloud Build):
    python -m pytest chatai/tests/test_roles.py -v --tb=short
"""

import os
import sys
from pathlib import Path

import pytest

# Resolve imports: backend/ and repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Cloud Build injects DATABASE_URL from Secret Manager — parse it into
# individual env vars that db.get_connection() expects.
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url and not os.environ.get("DB_HOST"):
    from urllib.parse import urlparse, unquote
    _u = urlparse(_db_url)
    os.environ["DB_USER"]     = unquote(_u.username or "")
    os.environ["DB_PASSWORD"] = unquote(_u.password or "")
    os.environ["DB_HOST"]     = _u.hostname or ""
    os.environ["DB_PORT"]     = str(_u.port or 5432)
    os.environ["DB_NAME"]     = _u.path.lstrip("/")

from db import get_connection
from auth import get_user_role

# ---------------------------------------------------------------------------
# Expected role assignments — source of truth for every deploy
# ---------------------------------------------------------------------------

EXPECTED_ADMINS = [
    "acastro@empresasdonar.cl",
    "fdonoso@empresasdonar.cl",
    "jgh@empresasdonar.cl",
    "gestion@empresasdonar.cl",
    "remuneraciones@empresasdonar.cl",
]

EXPECTED_USERS = [
    "administracion@empresasdonar.cl",
    "contabilidad@empresasdonar.cl",
    "adquisiciones@empresasdonar.cl",
    "operacionesislademaipo@empresasdonar.cl",
    "operacioneszuniga@empresasdonar.cl",
    "tecnicozuniga@empresasdonar.cl",
    "tecniconorte@empresasdonar.cl",
]

SENSITIVE_TABLES = ["Remuneraciones", "Nomina", "Cuentas_por_cobrar", "Pedidos_de_Venta"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def all_roles(db):
    with db.cursor() as cur:
        cur.execute("SELECT email, role FROM public.user_roles")
        return {row[0]: row[1] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# Table structure
# ---------------------------------------------------------------------------

def test_user_roles_table_exists(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user_roles'
            )
        """)
        assert cur.fetchone()[0], "FATAL: tabla public.user_roles no existe"


def test_user_roles_columns(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'user_roles'
        """)
        cols = {row[0] for row in cur.fetchall()}
    assert "email" in cols, "Falta columna 'email'"
    assert "role" in cols, "Falta columna 'role'"
    assert "created_at" in cols, "Falta columna 'created_at'"
    assert "updated_at" in cols, "Falta columna 'updated_at'"


def test_table_is_not_empty(all_roles):
    assert len(all_roles) > 0, (
        "FATAL: user_roles está vacía — el sistema de roles no está configurado"
    )


# ---------------------------------------------------------------------------
# Admin assignments
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("email", EXPECTED_ADMINS)
def test_admin_role_assigned(email, all_roles):
    assert email in all_roles, f"FALTA: {email} no tiene rol asignado"
    assert all_roles[email] == "admin", (
        f"ROL INCORRECTO: {email} tiene rol '{all_roles[email]}', esperado 'admin'"
    )


@pytest.mark.parametrize("email", EXPECTED_ADMINS)
def test_get_user_role_returns_admin(email):
    role = get_user_role(email)
    assert role == "admin", (
        f"get_user_role('{email}') retornó '{role}', esperado 'admin'"
    )


# ---------------------------------------------------------------------------
# User (restricted) assignments
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("email", EXPECTED_USERS)
def test_user_role_assigned(email, all_roles):
    assert email in all_roles, f"FALTA: {email} no tiene rol asignado"
    assert all_roles[email] == "user", (
        f"ROL INCORRECTO: {email} tiene rol '{all_roles[email]}', esperado 'user'"
    )


@pytest.mark.parametrize("email", EXPECTED_USERS)
def test_get_user_role_returns_user(email):
    role = get_user_role(email)
    assert role == "user", (
        f"get_user_role('{email}') retornó '{role}', esperado 'user'"
    )


# ---------------------------------------------------------------------------
# Unknown emails default to 'user' (never leak as admin)
# ---------------------------------------------------------------------------

def test_unknown_email_defaults_to_user():
    role = get_user_role("desconocido@empresasdonar.cl")
    assert role == "user", "Un email desconocido no debe obtener rol 'admin'"


def test_empty_email_defaults_to_user():
    assert get_user_role("") == "user"
    assert get_user_role(None) == "user"


# ---------------------------------------------------------------------------
# Role constraint — only valid values in DB
# ---------------------------------------------------------------------------

def test_no_invalid_roles(all_roles):
    invalid = {email: role for email, role in all_roles.items() if role not in ("admin", "user")}
    assert not invalid, f"Roles inválidos en DB: {invalid}"


# ---------------------------------------------------------------------------
# Coverage — all expected users are present
# ---------------------------------------------------------------------------

def test_all_expected_users_covered(all_roles):
    all_expected = set(EXPECTED_ADMINS + EXPECTED_USERS)
    missing = all_expected - set(all_roles.keys())
    assert not missing, f"Usuarios esperados sin rol asignado: {missing}"


def test_no_unexpected_admin_escalation(all_roles):
    """Ningún email fuera de EXPECTED_ADMINS debe tener rol admin."""
    expected_admin_set = set(EXPECTED_ADMINS)
    unexpected_admins = [
        email for email, role in all_roles.items()
        if role == "admin" and email not in expected_admin_set
    ]
    assert not unexpected_admins, (
        f"ESCALACIÓN DE PRIVILEGIOS: estos emails tienen admin sin estar en la lista autorizada: "
        f"{unexpected_admins}"
    )
